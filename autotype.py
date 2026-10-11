"""autotype - type the contents of a text file into the focused application.

Built for situations where clipboard paste is unavailable (remote and VM
consoles, locked-down sessions) and for live technical demonstrations.
Keystrokes are sent at a steady, configurable rate through PyAutoGUI.

Safety model, in order:
  1. The file is read and every character is checked against the platform's
     key map *before* anything is typed.
  2. Typing only starts after an explicit Enter confirmation (or ``--yes``)
     followed by a countdown of at least ``MIN_COUNTDOWN`` seconds.
  3. While typing, it stops immediately if the mouse is moved, if the
     PyAutoGUI fail-safe fires (mouse in a screen corner), or (on Windows) if
     keyboard focus changes to another window.
"""

from __future__ import annotations

import argparse
import codecs
import enum
import importlib
import logging
import math
import sys
import time
from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

__version__ = "2.0.0"

log = logging.getLogger("autotype")

DEFAULT_INPUT = Path("solution.txt")
DEFAULT_INTERVAL = 0.05
MIN_INTERVAL, MAX_INTERVAL = 0.0, 1.0
DEFAULT_COUNTDOWN = 5
MIN_COUNTDOWN, MAX_COUNTDOWN = 3, 60
MAX_FILE_BYTES = 1_000_000
MOUSE_GUARD_THRESHOLD_PX = 10
MAX_LISTED_ISSUES = 20

# Characters that every PyAutoGUI backend can type on a US-style layout. Used
# for dry runs when PyAutoGUI cannot be loaded.
PORTABLE_CHARS = frozenset(chr(c) for c in range(0x20, 0x7F)) | {"\n", "\t"}


class ExitCode(enum.IntEnum):
    OK = 0
    ERROR = 1  # unexpected internal error
    USAGE = 2  # invalid arguments (argparse also uses 2)
    INPUT = 3  # missing/empty/unreadable file, or unsupported characters
    DEPENDENCY = 4  # PyAutoGUI missing or no usable desktop session
    ABORTED = 5  # cancelled by the user or stopped by a safety guard
    INCOMPLETE = 6  # finished, but unsupported characters were skipped
    INTERRUPTED = 130  # Ctrl+C


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class AutotypeError(Exception):
    exit_code: ExitCode = ExitCode.ERROR


class UsageError(AutotypeError):
    exit_code = ExitCode.USAGE


class InputFileError(AutotypeError):
    exit_code = ExitCode.INPUT


class UnsupportedCharactersError(AutotypeError):
    exit_code = ExitCode.INPUT


class DependencyError(AutotypeError):
    exit_code = ExitCode.DEPENDENCY


class TypingAborted(AutotypeError):
    """Typing stopped before completion. ``sent`` is how many keystrokes were
    already delivered (``None`` if typing never started)."""

    exit_code = ExitCode.ABORTED

    def __init__(self, reason: str, sent: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.sent = sent


class TypingInterrupted(TypingAborted):
    exit_code = ExitCode.INTERRUPTED


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InputText:
    path: Path
    text: str
    newlines_normalized: bool = False
    bom_removed: bool = False
    indent_stripped: bool = False

    @property
    def line_count(self) -> int:
        return self.text.count("\n") + (0 if self.text.endswith("\n") else 1)


@dataclass(frozen=True)
class CharIssue:
    char: str
    line: int
    column: int

    def describe(self) -> str:
        # !a (ascii) keeps the report printable on consoles that are not UTF-8.
        return f"line {self.line}, column {self.column}: {self.char!a} (U+{ord(self.char):04X})"


def normalize_newlines(text: str) -> str:
    """Convert CRLF and lone CR line endings to LF (one Enter keystroke)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_indentation(text: str) -> str:
    """Remove leading spaces/tabs from each line, for editors that auto-indent."""
    return "\n".join(line.lstrip(" \t") for line in text.split("\n"))


def load_text(
    path: Path,
    *,
    encoding: str = "utf-8",
    strip_indent: bool = False,
    max_bytes: int = MAX_FILE_BYTES,
) -> InputText:
    shown = path.resolve()
    if not path.exists():
        raise InputFileError(f"input file not found: {shown}")
    if not path.is_file():
        raise InputFileError(f"input path is not a regular file: {shown}")
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise InputFileError(f"input file is too large ({size:,} bytes; limit {max_bytes:,}): {shown}")
        raw = path.read_bytes()
    except OSError as exc:
        raise InputFileError(f"cannot read {shown}: {exc.strerror or exc}") from exc

    if b"\x00" in raw:
        raise InputFileError(f"input file appears to be binary (contains NUL bytes): {shown}")
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise InputFileError(
            f"input file is not valid {encoding} (bad byte at offset {exc.start}): {shown}. "
            "Use --encoding to specify the correct encoding."
        ) from exc

    bom_removed = text.startswith("﻿")
    if bom_removed:
        text = text[1:]
    normalized = normalize_newlines(text)
    newlines_normalized = normalized != text
    text = normalized
    if strip_indent:
        text = strip_indentation(text)

    if not text.strip():
        raise InputFileError(f"input file is empty or contains only whitespace: {shown}")
    return InputText(
        path=shown,
        text=text,
        newlines_normalized=newlines_normalized,
        bom_removed=bom_removed,
        indent_stripped=strip_indent,
    )


def find_unsupported(text: str, supports: Callable[[str], bool]) -> list[CharIssue]:
    """Return the position of every character ``supports`` rejects."""
    cache: dict[str, bool] = {}
    issues: list[CharIssue] = []
    line, column = 1, 1
    for char in text:
        ok = cache.get(char)
        if ok is None:
            ok = cache[char] = supports(char)
        if not ok:
            issues.append(CharIssue(char, line, column))
        if char == "\n":
            line, column = line + 1, 1
        else:
            column += 1
    return issues


def format_issues(issues: list[CharIssue], limit: int = MAX_LISTED_ISSUES) -> str:
    lines = [f"  {issue.describe()}" for issue in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"  ... and {len(issues) - limit} more")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Desktop backend
# --------------------------------------------------------------------------


class Backend(Protocol):
    name: str

    def supports(self, char: str) -> bool: ...

    def press(self, char: str) -> None: ...

    def mouse_position(self) -> tuple[int, int]: ...

    def foreground_window(self) -> Hashable | None: ...

    def caps_lock_on(self) -> bool | None: ...


class PyAutoGuiBackend:
    """Sends keystrokes with PyAutoGUI, keeping its corner fail-safe enabled."""

    def __init__(self, pyautogui: Any, platform: str = sys.platform) -> None:
        self._gui = pyautogui
        self._platform = platform
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0  # pacing is done by type_text
        platform_module = getattr(pyautogui, "platformModule", None)
        self._mapping: dict[str, object] = dict(getattr(platform_module, "keyboardMapping", {}))
        version = getattr(pyautogui, "__version__", "?")
        self.name = f"PyAutoGUI {version} key map ({platform})"

    def supports(self, char: str) -> bool:
        # PyAutoGUI silently ignores keys it cannot map, so this check is the
        # only way to know a character will actually be sent.
        code = self._mapping.get(char)
        if not isinstance(code, int) or isinstance(code, bool) or code < 0:
            return False
        # On Windows the map comes from VkKeyScanA, whose low byte is 0xFF when
        # the active keyboard layout cannot produce the character.
        return not (self._platform == "win32" and code & 0xFF == 0xFF)

    def press(self, char: str) -> None:
        try:
            self._gui.write(char)
        except self._gui.FailSafeException as exc:
            raise TypingAborted("PyAutoGUI fail-safe triggered (mouse moved to a screen corner)") from exc

    def mouse_position(self) -> tuple[int, int]:
        x, y = self._gui.position()
        return int(x), int(y)

    def foreground_window(self) -> Hashable | None:
        return _win32_foreground_window() if self._platform == "win32" else None

    def caps_lock_on(self) -> bool | None:
        return _win32_caps_lock_on() if self._platform == "win32" else None


def _win32_foreground_window() -> int | None:
    if sys.platform != "win32":
        return None
    import ctypes

    handle = ctypes.windll.user32.GetForegroundWindow()
    return int(handle) if handle else None


def _win32_caps_lock_on() -> bool | None:
    if sys.platform != "win32":
        return None
    import ctypes

    return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)  # VK_CAPITAL toggle bit


def load_backend(import_module: Callable[[str], Any] = importlib.import_module) -> Backend:
    try:
        pyautogui = import_module("pyautogui")
    except ImportError as exc:
        raise DependencyError(
            "PyAutoGUI is not installed. Install it with: python -m pip install -r requirements.txt"
        ) from exc
    except Exception as exc:  # e.g. KeyError('DISPLAY') on a headless Linux box
        raise DependencyError(
            f"PyAutoGUI could not start ({type(exc).__name__}: {exc}). "
            "A graphical desktop session is required."
        ) from exc
    return PyAutoGuiBackend(pyautogui)


# --------------------------------------------------------------------------
# Typing
# --------------------------------------------------------------------------


class SafetyGuard:
    """Stops typing if the user moves the mouse or focus leaves the target."""

    def __init__(
        self,
        backend: Backend,
        *,
        watch_mouse: bool = True,
        launcher_window: Hashable | None = None,
        threshold: int = MOUSE_GUARD_THRESHOLD_PX,
    ) -> None:
        self._backend = backend
        self._watch_mouse = watch_mouse
        self._launcher = launcher_window
        self._threshold = threshold
        self._origin: tuple[int, int] | None = None
        self._target: Hashable | None = None

    def arm(self) -> None:
        """Snapshot the state right before the first keystroke."""
        target = self._backend.foreground_window()
        if target is not None and target == self._launcher:
            raise TypingAborted(
                "the terminal that launched autotype still has keyboard focus; "
                "click into the target window during the countdown"
            )
        if target is None:
            log.debug("focus-change guard unavailable on this platform")
        if self._backend.caps_lock_on():
            raise TypingAborted("Caps Lock is on, so letter case would be inverted; turn it off and retry")
        self._target = target
        if self._watch_mouse:
            self._origin = self._backend.mouse_position()

    def check(self) -> None:
        if self._origin is not None:
            x, y = self._backend.mouse_position()
            ox, oy = self._origin
            if max(abs(x - ox), abs(y - oy)) > self._threshold:
                raise TypingAborted("mouse movement detected")
        if self._target is not None and self._backend.foreground_window() != self._target:
            raise TypingAborted("keyboard focus moved to a different window")


def type_text(
    text: str,
    backend: Backend,
    *,
    interval: float,
    skip: Iterable[str] = (),
    guard: SafetyGuard | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Send ``text`` one keystroke at a time; returns the keystroke count.

    Characters in ``skip`` are not sent. Raises ``TypingAborted`` (with the
    number of keystrokes already sent) if a guard or the user stops it.
    """
    skipped = frozenset(skip)
    total = len(text)
    sent = 0
    try:
        for index, char in enumerate(text, start=1):
            if guard is not None:
                guard.check()
            if char not in skipped:
                backend.press(char)
                sent += 1
                if interval:
                    sleep(interval)
            if on_progress is not None:
                on_progress(index, total)
    except TypingAborted as exc:
        exc.sent = sent
        raise
    except KeyboardInterrupt:
        raise TypingInterrupted("interrupted with Ctrl+C", sent=sent) from None
    except Exception as exc:
        raise TypingAborted(f"keystroke delivery failed ({type(exc).__name__}: {exc})", sent=sent) from exc
    return sent


def countdown(seconds: int, sleep: Callable[[float], None] = time.sleep) -> None:
    for remaining in range(seconds, 0, -1):
        log.info("Typing starts in %d... (click into the target window now)", remaining)
        sleep(1)


class ProgressReporter:
    """Logs progress at 25% steps for longer inputs."""

    def __init__(self, min_chars: int = 200) -> None:
        self._min_chars = min_chars
        self._next = 25

    def __call__(self, done: int, total: int) -> None:
        if total < self._min_chars:
            return
        percent = done * 100 // total
        if percent >= self._next and done < total:
            log.info("%d%% sent (%d/%d characters)", percent, done, total)
            self._next = (percent // 25 + 1) * 25


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _number_in_range(kind: type[float] | type[int], low: float, high: float) -> Callable[[str], float]:
    def parse(value: str) -> float:
        try:
            number = kind(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected {kind.__name__}, got {value!r}") from None
        if not math.isfinite(number) or not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low:g} and {high:g}, got {value}")
        return number

    return parse


def _encoding(value: str) -> str:
    try:
        return codecs.lookup(value).name
    except LookupError:
        raise argparse.ArgumentTypeError(f"unknown encoding: {value!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotype",
        description=(
            "Type a text file into the focused application at a steady rate. "
            "Abort at any time by moving the mouse (or into a screen corner)."
        ),
        epilog=(
            "exit codes: 0 ok, 2 usage, 3 input/unsupported characters, 4 missing dependency, "
            "5 aborted, 6 finished with skipped characters, 130 Ctrl+C"
        ),
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"text file to type, relative to the current directory (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=_number_in_range(float, MIN_INTERVAL, MAX_INTERVAL),
        default=DEFAULT_INTERVAL,
        metavar="SECONDS",
        help=f"fixed delay after each keystroke, {MIN_INTERVAL:g}-{MAX_INTERVAL:g} "
        f"(default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "-c",
        "--countdown",
        type=_number_in_range(int, MIN_COUNTDOWN, MAX_COUNTDOWN),
        default=DEFAULT_COUNTDOWN,
        metavar="SECONDS",
        help=f"delay before typing starts, {MIN_COUNTDOWN}-{MAX_COUNTDOWN} (default: {DEFAULT_COUNTDOWN})",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="skip the 'press Enter to start' confirmation"
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="read and validate the file, print a report, and type nothing",
    )
    parser.add_argument(
        "--on-unsupported",
        choices=("abort", "skip"),
        default="abort",
        help="what to do with characters that cannot be typed (default: abort before typing)",
    )
    parser.add_argument(
        "--strip-indent",
        action="store_true",
        help="remove leading whitespace from every line (for editors that auto-indent)",
    )
    parser.add_argument(
        "--encoding",
        type=_encoding,
        default="utf-8",
        help="input file encoding (default: utf-8; a BOM is removed)",
    )
    parser.add_argument(
        "--no-mouse-guard",
        dest="mouse_guard",
        action="store_false",
        help="do not abort when the mouse moves (the corner fail-safe stays active)",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", help="show debug output")
    verbosity.add_argument("-q", "--quiet", action="store_true", help="show warnings and errors only")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


@dataclass
class Runtime:
    """Side-effecting dependencies, replaceable in tests."""

    backend_factory: Callable[[], Backend] = load_backend
    sleep: Callable[[float], None] = time.sleep
    prompt: Callable[[str], str] = input
    stdin_is_interactive: Callable[[], bool] = field(default=lambda: sys.stdin.isatty())
    out: Callable[[str], None] = print


def _describe_input(source: InputText, interval: float) -> list[str]:
    chars = len(source.text)
    notes = []
    if source.newlines_normalized:
        notes.append("CR/CRLF line endings converted to LF (one Enter per line)")
    if source.bom_removed:
        notes.append("byte-order mark removed")
    if source.indent_stripped:
        notes.append("leading indentation removed")
    lines = [
        f"  File:           {source.path}",
        f"  Characters:     {chars:,} ({source.line_count:,} line{'' if source.line_count == 1 else 's'})",
        f"  Est. duration:  ~{chars * interval:,.0f} s at {interval:g} s per keystroke",
    ]
    if notes:
        lines.append(f"  Adjustments:    {'; '.join(notes)}")
    tabs = source.text.count("\t")
    if tabs:
        lines.append(f"  Note:           {tabs} Tab keystroke(s); Tab may trigger completion or indentation")
    return lines


def _dry_run(args: argparse.Namespace, source: InputText, runtime: Runtime) -> ExitCode:
    try:
        backend = runtime.backend_factory()
        supports: Callable[[str], bool] = backend.supports
        ruleset = backend.name
    except DependencyError as exc:
        supports = PORTABLE_CHARS.__contains__
        ruleset = f"portable ASCII set (PyAutoGUI unavailable: {exc})"

    issues = find_unsupported(source.text, supports)
    out = runtime.out
    out("Dry run: nothing will be typed.")
    for line in _describe_input(source, args.interval):
        out(line)
    out(f"  Key check:      {ruleset}")
    if not issues:
        out("  Unsupported:    none")
        out("Result: ready to type.")
        return ExitCode.OK
    out(f"  Unsupported:    {len(issues)} character(s)")
    out(format_issues(issues))
    if args.on_unsupported == "skip":
        out(f"Result: would type with {len(issues)} character(s) omitted (--on-unsupported skip).")
        return ExitCode.INCOMPLETE
    out("Result: would refuse to type. Fix the file or pass --on-unsupported skip.")
    return ExitCode.INPUT


def run(args: argparse.Namespace, runtime: Runtime) -> ExitCode:
    source = load_text(args.file, encoding=args.encoding, strip_indent=args.strip_indent)
    if args.dry_run:
        return _dry_run(args, source, runtime)

    if not args.yes and not runtime.stdin_is_interactive():
        raise UsageError("standard input is not interactive; pass --yes to start without confirmation")

    backend = runtime.backend_factory()
    issues = find_unsupported(source.text, backend.supports)
    skip = {issue.char for issue in issues}
    if issues and args.on_unsupported == "abort":
        raise UnsupportedCharactersError(
            f"{len(issues)} character(s) cannot be typed with {backend.name}; nothing was typed:\n"
            f"{format_issues(issues)}\n"
            "Fix the file, or pass --on-unsupported skip to omit them."
        )
    if issues:
        log.warning("%d unsupported character(s) will be SKIPPED:\n%s", len(issues), format_issues(issues))

    for line in _describe_input(source, args.interval):
        log.info("%s", line.strip())
    log.info(
        "To abort while typing: %s.",
        "move the mouse (any movement stops it), or push it into a screen corner"
        if args.mouse_guard
        else "push the mouse into a screen corner (PyAutoGUI fail-safe)",
    )

    if not args.yes:
        try:
            answer = runtime.prompt("Press Enter to start the countdown, or type q then Enter to cancel: ")
        except EOFError:
            answer = "q"
        if answer.strip().lower() in {"q", "quit", "n", "no"}:
            log.info("Cancelled; nothing was typed.")
            return ExitCode.ABORTED

    launcher = backend.foreground_window()
    countdown(args.countdown, runtime.sleep)

    guard = SafetyGuard(backend, watch_mouse=args.mouse_guard, launcher_window=launcher)
    guard.arm()
    sent = type_text(
        source.text,
        backend,
        interval=args.interval,
        skip=skip,
        guard=guard,
        sleep=runtime.sleep,
        on_progress=ProgressReporter(),
    )

    if issues:
        log.warning(
            "Sent %d keystrokes; %d character(s) were NOT typed (listed above). "
            "The result in the target window is incomplete.",
            sent,
            len(issues),
        )
        return ExitCode.INCOMPLETE
    log.info(
        "Sent all %d keystrokes. Review the target window: auto-indent, auto-closing "
        "brackets or input lag in the target can alter what appears.",
        sent,
    )
    return ExitCode.OK


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.levelno >= logging.WARNING:
            return f"autotype: {record.levelname.lower()}: {message}"
        return f"autotype: {message}"


def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    for handler in list(log.handlers):
        log.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO)
    log.propagate = False


def _make_output_encoding_safe() -> None:
    """Escape characters the console cannot encode (e.g. cp1252) instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def main(argv: list[str] | None = None, runtime: Runtime | None = None) -> int:
    _make_output_encoding_safe()
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose, args.quiet)
    try:
        return int(run(args, runtime or Runtime()))
    except TypingAborted as exc:
        if exc.sent is None:
            log.error("aborted: %s. Nothing was typed.", exc.reason)
        else:
            log.error(
                "aborted: %s. %d keystroke(s) had already been sent; the target contains partial text.",
                exc.reason,
                exc.sent,
            )
        return int(exc.exit_code)
    except AutotypeError as exc:
        log.error("%s", exc)
        return int(exc.exit_code)
    except KeyboardInterrupt:
        log.error("interrupted with Ctrl+C before typing started. Nothing was typed.")
        return int(ExitCode.INTERRUPTED)
    except Exception as exc:  # last-resort guard so users get a clear message
        log.debug("unexpected error", exc_info=True)
        log.error("unexpected error: %s: %s (rerun with -v for details)", type(exc).__name__, exc)
        return int(ExitCode.ERROR)


if __name__ == "__main__":
    sys.exit(main())
