from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Hashable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import autotype
from autotype import (
    PORTABLE_CHARS,
    DependencyError,
    ExitCode,
    InputFileError,
    PyAutoGuiBackend,
    Runtime,
    SafetyGuard,
    TypingAborted,
    find_unsupported,
    load_backend,
    load_text,
    main,
    type_text,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class FakeBackend:
    """Records keystrokes in a shared event log instead of touching the desktop."""

    name = "fake key map"

    def __init__(
        self,
        events: list[tuple[str, Any]] | None = None,
        *,
        unsupported: str = "",
        mouse: Iterator[tuple[int, int]] | None = None,
        windows: Iterator[Hashable | None] | None = None,
        caps_lock: bool | None = False,
        fail_at: int | None = None,
        fail_with: BaseException | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.unsupported = set(unsupported)
        self._mouse = mouse
        self._windows = windows
        self._caps = caps_lock
        self._fail_at = fail_at
        self._fail_with = fail_with

    @property
    def typed(self) -> str:
        return "".join(value for kind, value in self.events if kind == "press")

    def supports(self, char: str) -> bool:
        return char in PORTABLE_CHARS and char not in self.unsupported

    def press(self, char: str) -> None:
        if self._fail_at is not None and len(self.typed) == self._fail_at:
            assert self._fail_with is not None
            raise self._fail_with
        self.events.append(("press", char))

    def mouse_position(self) -> tuple[int, int]:
        return next(self._mouse) if self._mouse is not None else (100, 100)

    def foreground_window(self) -> Hashable | None:
        return next(self._windows) if self._windows is not None else None

    def caps_lock_on(self) -> bool | None:
        return self._caps


def repeat(first: Any, *, then: Any = None, after: int = 0) -> Iterator[Any]:
    """Yield ``first`` ``after`` times, then ``then`` forever (or ``first``)."""
    for _ in range(after):
        yield first
    while True:
        yield then if after else first


def make_runtime(
    backend: FakeBackend,
    *,
    answer: str | BaseException = "",
    interactive: bool = True,
    sleep_error: BaseException | None = None,
) -> tuple[Runtime, list[str]]:
    output: list[str] = []

    def sleep(seconds: float) -> None:
        backend.events.append(("sleep", seconds))
        if sleep_error is not None:
            raise sleep_error

    def prompt(message: str) -> str:
        backend.events.append(("prompt", message))
        if isinstance(answer, BaseException):
            raise answer
        return answer

    runtime = Runtime(
        backend_factory=lambda: backend,
        sleep=sleep,
        prompt=prompt,
        stdin_is_interactive=lambda: interactive,
        out=output.append,
    )
    return runtime, output


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    path = tmp_path / "snippet.txt"
    path.write_bytes(b"int x = 1;\r\nreturn x;")
    return path


# --------------------------------------------------------------------------
# load_text
# --------------------------------------------------------------------------


class TestLoadText:
    def test_normalizes_crlf_and_reports_it(self, sample: Path) -> None:
        source = load_text(sample)
        assert source.text == "int x = 1;\nreturn x;"
        assert source.newlines_normalized
        assert source.line_count == 2

    def test_lone_cr_is_normalized(self, tmp_path: Path) -> None:
        path = tmp_path / "mac.txt"
        path.write_bytes(b"a\rb\r")
        assert load_text(path).text == "a\nb\n"

    def test_lf_file_is_unchanged(self, tmp_path: Path) -> None:
        path = tmp_path / "unix.txt"
        path.write_bytes(b"a\n\tb\n")
        source = load_text(path)
        assert source.text == "a\n\tb\n"
        assert not source.newlines_normalized

    def test_strips_utf8_bom(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfhello")
        source = load_text(path)
        assert source.text == "hello"
        assert source.bom_removed

    def test_strip_indent(self, tmp_path: Path) -> None:
        path = tmp_path / "indented.txt"
        path.write_text("if (x) {\n    y();\n\t}\n", encoding="utf-8")
        assert load_text(path, strip_indent=True).text == "if (x) {\ny();\n}\n"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(InputFileError, match="not found"):
            load_text(tmp_path / "nope.txt")

    def test_directory(self, tmp_path: Path) -> None:
        with pytest.raises(InputFileError, match="not a regular file"):
            load_text(tmp_path)

    @pytest.mark.parametrize("content", [b"", b"  \r\n\t \n"])
    def test_empty_or_whitespace(self, tmp_path: Path, content: bytes) -> None:
        path = tmp_path / "empty.txt"
        path.write_bytes(content)
        with pytest.raises(InputFileError, match="empty"):
            load_text(path)

    def test_binary(self, tmp_path: Path) -> None:
        path = tmp_path / "blob.bin"
        path.write_bytes(b"abc\x00def")
        with pytest.raises(InputFileError, match="binary"):
            load_text(path)

    def test_invalid_encoding_suggests_flag(self, tmp_path: Path) -> None:
        path = tmp_path / "latin1.txt"
        path.write_bytes("café".encode("latin-1"))
        with pytest.raises(InputFileError, match="--encoding"):
            load_text(path)
        assert load_text(path, encoding="latin-1").text == "café"

    def test_too_large(self, tmp_path: Path) -> None:
        path = tmp_path / "big.txt"
        path.write_text("x" * 101, encoding="utf-8")
        with pytest.raises(InputFileError, match="too large"):
            load_text(path, max_bytes=100)


# --------------------------------------------------------------------------
# Character support
# --------------------------------------------------------------------------


def test_find_unsupported_reports_line_and_column() -> None:
    issues = find_unsupported("ab\ncé\n→", PORTABLE_CHARS.__contains__)
    assert [(i.char, i.line, i.column) for i in issues] == [("é", 2, 2), ("→", 3, 1)]
    assert "U+00E9" in issues[0].describe()
    assert issues[1].describe().isascii()  # safe to print on any console


def test_portable_chars_cover_code_but_not_carriage_return() -> None:
    assert set("{}[]();<>=+-*/&|!~^%#@$`'\"\\ \n\t") <= PORTABLE_CHARS
    assert "\r" not in PORTABLE_CHARS


class FailSafe(Exception):
    pass


def fake_pyautogui(mapping: dict[str, Any]) -> SimpleNamespace:
    module = SimpleNamespace(
        FAILSAFE=False,
        PAUSE=0.1,
        __version__="9.9",
        FailSafeException=FailSafe,
        platformModule=SimpleNamespace(keyboardMapping=mapping),
        written=[],
    )
    module.write = module.written.append
    module.position = lambda: (5.0, 7.0)
    return module


class TestPyAutoGuiBackend:
    def test_enables_failsafe_and_disables_builtin_pause(self) -> None:
        module = fake_pyautogui({})
        PyAutoGuiBackend(module, platform="linux")
        assert module.FAILSAFE is True
        assert module.PAUSE == 0

    def test_supports_uses_platform_key_map(self) -> None:
        mapping = {"a": 65, "\n": 13, "\r": None, "é": -1, "§": 0x01FF, "x": True}
        backend = PyAutoGuiBackend(fake_pyautogui(mapping), platform="win32")
        assert backend.supports("a")
        assert backend.supports("\n")
        assert not backend.supports("\r")  # mapped to None: PyAutoGUI would drop it
        assert not backend.supports("é")  # VkKeyScanA returned -1
        assert not backend.supports("§")  # low byte 0xFF: layout cannot produce it
        assert not backend.supports("x")
        assert not backend.supports("→")  # absent from the map

    def test_low_byte_ff_is_only_special_on_windows(self) -> None:
        backend = PyAutoGuiBackend(fake_pyautogui({"k": 0xFF}), platform="linux")
        assert backend.supports("k")

    def test_press_writes_and_translates_failsafe(self) -> None:
        module = fake_pyautogui({})
        backend = PyAutoGuiBackend(module, platform="linux")
        backend.press("q")
        assert module.written == ["q"]

        def explode(_: str) -> None:
            raise FailSafe("corner")

        module.write = explode
        with pytest.raises(TypingAborted, match="fail-safe"):
            backend.press("q")

    def test_non_windows_has_no_focus_or_caps_lock_probe(self) -> None:
        backend = PyAutoGuiBackend(fake_pyautogui({}), platform="darwin")
        assert backend.foreground_window() is None
        assert backend.caps_lock_on() is None
        assert backend.mouse_position() == (5, 7)


class TestLoadBackend:
    def test_missing_pyautogui(self) -> None:
        # conftest makes the import fail, exactly like an uninstalled package.
        with pytest.raises(DependencyError, match="not installed"):
            load_backend()

    def test_pyautogui_crashes_on_import(self) -> None:
        def broken(name: str) -> None:
            raise KeyError("DISPLAY")

        with pytest.raises(DependencyError, match="graphical desktop"):
            load_backend(broken)

    def test_loads_and_wraps_module(self) -> None:
        module = fake_pyautogui({"a": 65})
        backend = load_backend(lambda name: module)
        assert backend.supports("a")
        assert module.FAILSAFE is True


# --------------------------------------------------------------------------
# type_text and the safety guard
# --------------------------------------------------------------------------


class TestTypeText:
    def test_types_every_char_with_steady_interval(self) -> None:
        backend = FakeBackend()
        sleeps: list[float] = []
        sent = type_text("ab\nc", backend, interval=0.02, sleep=sleeps.append)
        assert sent == 4
        assert backend.typed == "ab\nc"
        assert sleeps == [0.02] * 4  # identical delay after every keystroke

    def test_zero_interval_never_sleeps(self) -> None:
        sleeps: list[float] = []
        type_text("abc", FakeBackend(), interval=0, sleep=sleeps.append)
        assert sleeps == []

    def test_skip_set_is_not_sent(self) -> None:
        backend = FakeBackend()
        sent = type_text("aéb", backend, interval=0, skip={"é"})
        assert (sent, backend.typed) == (2, "ab")

    def test_abort_reports_keystrokes_already_sent(self) -> None:
        backend = FakeBackend(fail_at=3, fail_with=TypingAborted("fail-safe"))
        with pytest.raises(TypingAborted) as info:
            type_text("abcdef", backend, interval=0)
        assert info.value.sent == 3
        assert backend.typed == "abc"

    def test_ctrl_c_mid_typing_becomes_interrupted(self) -> None:
        backend = FakeBackend(fail_at=2, fail_with=KeyboardInterrupt())
        with pytest.raises(autotype.TypingInterrupted) as info:
            type_text("abcdef", backend, interval=0)
        assert info.value.sent == 2
        assert info.value.exit_code == ExitCode.INTERRUPTED

    def test_unexpected_backend_error_is_wrapped_with_count(self) -> None:
        backend = FakeBackend(fail_at=1, fail_with=OSError("device gone"))
        with pytest.raises(TypingAborted, match="device gone") as info:
            type_text("abc", backend, interval=0)
        assert info.value.sent == 1

    def test_mouse_movement_stops_typing(self) -> None:
        backend = FakeBackend(mouse=repeat((100, 100), then=(140, 100), after=3))
        guard = SafetyGuard(backend)
        guard.arm()  # consumes the first position
        with pytest.raises(TypingAborted, match="mouse movement") as info:
            type_text("abcdef", backend, interval=0, guard=guard)
        assert info.value.sent == 2

    def test_small_mouse_jitter_is_tolerated(self) -> None:
        backend = FakeBackend(mouse=repeat((100, 100), then=(105, 96), after=1))
        guard = SafetyGuard(backend)
        guard.arm()
        assert type_text("abc", backend, interval=0, guard=guard) == 3

    def test_focus_change_stops_typing(self) -> None:
        backend = FakeBackend(windows=repeat(42, then=99, after=3))
        guard = SafetyGuard(backend, watch_mouse=False, launcher_window=7)
        guard.arm()
        with pytest.raises(TypingAborted, match="focus moved") as info:
            type_text("abcdef", backend, interval=0, guard=guard)
        assert info.value.sent == 2

    def test_refuses_to_type_into_launching_terminal(self) -> None:
        backend = FakeBackend(windows=repeat(7))
        guard = SafetyGuard(backend, launcher_window=7)
        with pytest.raises(TypingAborted, match="still has keyboard focus"):
            guard.arm()

    def test_refuses_when_caps_lock_is_on(self) -> None:
        guard = SafetyGuard(FakeBackend(caps_lock=True))
        with pytest.raises(TypingAborted, match="Caps Lock"):
            guard.arm()


# --------------------------------------------------------------------------
# Command line: argument validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["-i", "-0.1"],
        ["-i", "1.5"],
        ["-i", "nan"],
        ["-i", "fast"],
        ["-c", "2"],
        ["-c", "61"],
        ["-c", "3.5"],
        ["--encoding", "klingon"],
        ["--on-unsupported", "replace"],
        ["-v", "-q"],
    ],
)
def test_invalid_arguments_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main([*argv, "--dry-run"])
    assert info.value.code == 2
    assert "error" in capsys.readouterr().err


def test_default_file_is_solution_txt_in_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "solution.txt").write_text("hi", encoding="utf-8")
    args = autotype.build_parser().parse_args([])
    assert args.file == Path("solution.txt")
    assert load_text(args.file).path == tmp_path / "solution.txt"


# --------------------------------------------------------------------------
# Command line: dry run
# --------------------------------------------------------------------------


class TestDryRun:
    def test_reports_and_types_nothing(self, sample: Path) -> None:
        backend = FakeBackend()
        runtime, output = make_runtime(backend)
        assert main([str(sample), "--dry-run"], runtime) == ExitCode.OK
        assert backend.events == []  # no prompt, no countdown, no keystrokes
        report = "\n".join(output)
        assert "nothing will be typed" in report
        assert "Characters:     20 (2 lines)" in report
        assert "CRLF" in report
        assert "ready to type" in report

    def test_unsupported_chars_fail_by_default(self, tmp_path: Path) -> None:
        path = tmp_path / "u.txt"
        path.write_text("print('é')", encoding="utf-8")
        runtime, output = make_runtime(FakeBackend())
        assert main([str(path), "-n"], runtime) == ExitCode.INPUT
        assert "line 1, column 8" in "\n".join(output)

    def test_unsupported_chars_with_skip_policy(self, tmp_path: Path) -> None:
        path = tmp_path / "u.txt"
        path.write_text("x = 'é'", encoding="utf-8")
        runtime, output = make_runtime(FakeBackend())
        assert main([str(path), "-n", "--on-unsupported", "skip"], runtime) == ExitCode.INCOMPLETE
        assert "omitted" in "\n".join(output)

    def test_falls_back_to_portable_set_without_pyautogui(self, sample: Path) -> None:
        output: list[str] = []
        runtime = Runtime(out=output.append)  # real load_backend; import is blocked
        assert main([str(sample), "--dry-run"], runtime) == ExitCode.OK
        assert "portable ASCII set" in "\n".join(output)

    def test_warns_about_tabs(self, tmp_path: Path) -> None:
        path = tmp_path / "t.txt"
        path.write_text("a\tb", encoding="utf-8")
        runtime, output = make_runtime(FakeBackend())
        main([str(path), "-n"], runtime)
        assert "1 Tab keystroke" in "\n".join(output)


# --------------------------------------------------------------------------
# Command line: live runs (fake backend only)
# --------------------------------------------------------------------------


class TestLiveRun:
    def test_confirm_then_countdown_then_type(self, sample: Path) -> None:
        backend = FakeBackend()
        runtime, _ = make_runtime(backend)
        code = main([str(sample), "--countdown", "3", "--interval", "0.01"], runtime)
        assert code == ExitCode.OK
        assert backend.typed == "int x = 1;\nreturn x;"
        kinds = [kind for kind, _ in backend.events]
        first_press = kinds.index("press")
        # Prompt first, then the full 3 s countdown, and only then keystrokes.
        assert kinds[:first_press] == ["prompt", "sleep", "sleep", "sleep"]
        assert [v for k, v in backend.events[:first_press] if k == "sleep"] == [1, 1, 1]
        assert {v for k, v in backend.events[first_press:] if k == "sleep"} == {0.01}

    def test_yes_skips_prompt_but_keeps_countdown(self, sample: Path) -> None:
        backend = FakeBackend()
        runtime, _ = make_runtime(backend, interactive=False)
        assert main([str(sample), "--yes"], runtime) == ExitCode.OK
        kinds = [kind for kind, _ in backend.events]
        assert "prompt" not in kinds
        assert kinds[:5] == ["sleep"] * 5  # default countdown is 5 s

    @pytest.mark.parametrize("answer", ["q", "Q\n", "no", EOFError()])
    def test_cancel_at_prompt_types_nothing(self, sample: Path, answer: str | BaseException) -> None:
        backend = FakeBackend()
        runtime, _ = make_runtime(backend, answer=answer)
        assert main([str(sample)], runtime) == ExitCode.ABORTED
        assert backend.typed == ""
        assert [k for k, _ in backend.events] == ["prompt"]

    def test_non_interactive_without_yes_types_nothing(self, sample: Path) -> None:
        backend = FakeBackend()
        runtime, _ = make_runtime(backend, interactive=False)
        assert main([str(sample)], runtime) == ExitCode.USAGE
        assert backend.events == []

    def test_unsupported_chars_abort_before_anything_is_typed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "u.txt"
        path.write_text("a = 'ü'", encoding="utf-8")
        backend = FakeBackend()
        runtime, _ = make_runtime(backend)
        assert main([str(path)], runtime) == ExitCode.INPUT
        assert backend.events == []
        assert "nothing was typed" in capsys.readouterr().err

    def test_skip_policy_types_rest_and_reports_incomplete(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "u.txt"
        path.write_text("a = 'ü'", encoding="utf-8")
        backend = FakeBackend()
        runtime, _ = make_runtime(backend)
        assert main([str(path), "--on-unsupported", "skip"], runtime) == ExitCode.INCOMPLETE
        assert backend.typed == "a = ''"
        err = capsys.readouterr().err
        assert "will be SKIPPED" in err
        assert "NOT typed" in err
        assert "Sent all" not in err

    def test_success_message_does_not_overclaim(
        self, sample: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runtime, _ = make_runtime(FakeBackend())
        main([str(sample)], runtime)
        err = capsys.readouterr().err
        assert "Sent all 20 keystrokes" in err
        assert "Review the target window" in err

    def test_failsafe_mid_typing_reports_partial(
        self, sample: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        backend = FakeBackend(fail_at=4, fail_with=TypingAborted("PyAutoGUI fail-safe triggered"))
        runtime, _ = make_runtime(backend)
        assert main([str(sample)], runtime) == ExitCode.ABORTED
        assert backend.typed == "int "
        assert "4 keystroke(s) had already been sent" in capsys.readouterr().err

    def test_focus_still_on_terminal_types_nothing(
        self, sample: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        backend = FakeBackend(windows=repeat(7))
        runtime, _ = make_runtime(backend)
        assert main([str(sample)], runtime) == ExitCode.ABORTED
        assert backend.typed == ""
        assert "Nothing was typed" in capsys.readouterr().err

    def test_mouse_guard_can_be_disabled(self, sample: Path) -> None:
        moving = iter((x, 0) for x in range(0, 10_000, 50))
        backend = FakeBackend(mouse=moving)
        runtime, _ = make_runtime(backend)
        assert main([str(sample), "--no-mouse-guard"], runtime) == ExitCode.OK
        assert len(backend.typed) == 20

    def test_mouse_guard_is_on_by_default(self, sample: Path) -> None:
        moving = iter((x, 0) for x in range(0, 10_000, 50))
        backend = FakeBackend(mouse=moving)
        runtime, _ = make_runtime(backend)
        assert main([str(sample)], runtime) == ExitCode.ABORTED

    def test_ctrl_c_during_countdown(self, sample: Path, capsys: pytest.CaptureFixture[str]) -> None:
        backend = FakeBackend()
        runtime, _ = make_runtime(backend, sleep_error=KeyboardInterrupt())
        assert main([str(sample)], runtime) == ExitCode.INTERRUPTED
        assert backend.typed == ""
        assert "Nothing was typed" in capsys.readouterr().err

    def test_missing_dependency(self, sample: Path, capsys: pytest.CaptureFixture[str]) -> None:
        runtime = Runtime(prompt=lambda _: "", stdin_is_interactive=lambda: True)
        assert main([str(sample)], runtime) == ExitCode.DEPENDENCY
        assert "pip install -r requirements.txt" in capsys.readouterr().err

    def test_missing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        runtime, _ = make_runtime(FakeBackend())
        assert main([str(tmp_path / "absent.txt")], runtime) == ExitCode.INPUT
        assert "not found" in capsys.readouterr().err

    def test_unexpected_error_is_reported_cleanly(
        self, sample: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def broken() -> FakeBackend:
            raise RuntimeError("boom")

        runtime = Runtime(backend_factory=broken, stdin_is_interactive=lambda: True)
        assert main([str(sample)], runtime) == ExitCode.ERROR
        assert "unexpected error: RuntimeError: boom" in capsys.readouterr().err

    def test_progress_logged_for_long_input(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "long.txt"
        path.write_text("x" * 400, encoding="utf-8")
        runtime, _ = make_runtime(FakeBackend())
        assert main([str(path), "-y", "-i", "0"], runtime) == ExitCode.OK
        err = capsys.readouterr().err
        assert "25% sent" in err and "75% sent" in err


# --------------------------------------------------------------------------
# Entry points (subprocess; dry run only, so nothing is ever typed)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("script", ["autotype.py", "typer.py"])
def test_entry_points_dry_run(script: str, sample: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_DIR / script), str(sample), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "ready to type" in result.stdout


def test_unsupported_report_survives_non_utf8_console(tmp_path: Path) -> None:
    path = tmp_path / "arrow.txt"
    path.write_text("a \u2192 b", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "autotype.py"), str(path), "--dry-run"],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
        timeout=60,
    )
    assert result.returncode == ExitCode.INPUT, result.stderr
    assert b"U+2192" in result.stdout


def test_entry_point_version() -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "autotype.py"), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert autotype.__version__ in result.stdout
