# autotype

Types the contents of a text file into the focused application, one keystroke
at a time, at a **steady, configurable rate**.

Intended uses:

- entering code or config into **remote, VM, KVM/noVNC or serial-over-web
  consoles** where clipboard paste does not work;
- locked-down sessions where paste is disabled by policy you are permitted to
  work around (e.g. your own lab machines);
- **live technical demonstrations** where you want code to appear predictably.

It deliberately sends keystrokes at a constant interval and does not try to
imitate human typing. Do not use it to get around paste detection,
keystroke-analysis or other integrity controls in exams, assessments, contests
or interviews.

## Requirements

- Python 3.9 or newer (written for 3.9+; tested on 3.13)
- A graphical desktop session (Windows, macOS, or Linux on X11)
- [PyAutoGUI](https://pyautogui.readthedocs.io/) 0.9.54+ (see `requirements.txt`)

## Installation

```bash
python -m pip install -r requirements.txt
```

For development (tests, linting, type checking):

```bash
python -m pip install -r requirements-dev.txt
```

Using a virtual environment is recommended:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # macOS / Linux
python -m pip install -r requirements.txt
```

## Usage

```bash
python autotype.py [options] [FILE]
```

`FILE` defaults to `solution.txt` **in the current directory**. `python typer.py`
still works and behaves identically (it is a thin wrapper around `autotype.py`).

### Always start with a dry run

```bash
python autotype.py --dry-run solution.txt
```

The dry run reads and validates the file, checks every character against the
platform key map, and prints a report. It never types anything.

```text
Dry run: nothing will be typed.
  File:           C:\...\solution.txt
  Characters:     935 (57 lines)
  Est. duration:  ~47 s at 0.05 s per keystroke
  Adjustments:    CR/CRLF line endings converted to LF (one Enter per line)
  Key check:      PyAutoGUI 0.9.54 key map (win32)
  Unsupported:    none
Result: ready to type.
```

### Typing

```bash
python autotype.py solution.txt
```

1. autotype validates the file and prints a summary.
2. It asks you to **press Enter** to begin (type `q` to cancel).
3. A **countdown** (default 5 s, minimum 3 s) runs; click into the target
   window during it.
4. Keys are sent at a fixed interval. A final message reports how many
   keystrokes were sent.

### Examples

```bash
# Slower, for a laggy remote console
python autotype.py --interval 0.15 deploy.sh

# Longer countdown to reach a window on another monitor
python autotype.py --countdown 10 config.yaml

# Editor that auto-indents: drop the file's own indentation
python autotype.py --strip-indent snippet.py

# Type everything except characters the keyboard map cannot produce
python autotype.py --on-unsupported skip notes.txt

# Non-interactive start (still waits for the countdown)
python autotype.py --yes --countdown 5 commands.txt

# Windows-1252 encoded input
python autotype.py --encoding cp1252 legacy.txt
```

### Options

| Option | Default | Description |
| --- | --- | --- |
| `FILE` | `solution.txt` | Text file to type, relative to the current directory. |
| `-i`, `--interval SECONDS` | `0.05` | Fixed delay after every keystroke (0–1). |
| `-c`, `--countdown SECONDS` | `5` | Delay before typing starts (3–60, whole seconds). |
| `-y`, `--yes` | off | Skip the "press Enter" confirmation. The countdown still runs. |
| `-n`, `--dry-run` | off | Validate and report; type nothing. |
| `--on-unsupported {abort,skip}` | `abort` | `abort` refuses to type anything if any character is unsupported. `skip` types the rest and exits with code 6. |
| `--strip-indent` | off | Remove leading spaces/tabs from each line. |
| `--encoding NAME` | `utf-8` | Input encoding. A UTF-8 BOM is always removed. |
| `--no-mouse-guard` | off | Don't abort on mouse movement (corner fail-safe remains). |
| `-v` / `-q` | | Debug output / warnings and errors only (`-q` also hides the countdown messages). |
| `--version` | | Print the version. |

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All keystrokes sent. |
| 1 | Unexpected internal error (rerun with `-v`). |
| 2 | Invalid arguments, or no `--yes` when stdin is not interactive. |
| 3 | Input problem: missing, empty, binary, too large (> 1 MB), wrong encoding, or unsupported characters with `--on-unsupported abort`. |
| 4 | PyAutoGUI missing or no usable desktop session. |
| 5 | Cancelled at the prompt, or stopped by a safety guard / fail-safe. |
| 6 | Finished, but unsupported characters were skipped. The target text is incomplete. |
| 130 | Interrupted with Ctrl+C. |

## Safety

autotype sends real keystrokes to whichever window has focus. Text containing
newlines presses **Enter**, which in a shell **executes each line as it is
typed**.

Built-in protections:

- **Nothing is typed before you confirm.** Typing needs an Enter confirmation
  (or `--yes`) followed by a countdown of at least 3 seconds. Without `--yes`, a
  non-interactive stdin is refused.
- **All checks run before the first keystroke.** File errors and unsupported
  characters are reported before typing begins, never part-way through.
- **Moving the mouse stops typing immediately** (more than 10 px from where
  it was when typing began). Disable with `--no-mouse-guard`.
- **PyAutoGUI's fail-safe is always on.** Moving the mouse into any screen
  corner stops typing.
- **Focus guards (Windows):** autotype refuses to start if the terminal that
  launched it still has focus when the countdown ends, and it stops if focus
  moves to a different window while typing.
- **Caps Lock check (Windows):** autotype refuses to start while Caps Lock is
  on, because Caps Lock would invert the case of every letter.
- **Honest reporting.** If typing stops early, the message says how many
  keystrokes were already sent, so you know the target holds partial text.

Precautions:

- Run `--dry-run` first.
- Don't touch the keyboard while typing runs. A held modifier key (Ctrl, Alt,
  Win) turns the typed characters into shortcuts.
- In a shell, review the file first: every line runs when its Enter is sent.
- Ctrl+C only reaches autotype while its terminal has focus. That's usually
  not the case once typing has started, so use the mouse to abort.

## Supported platforms

| Platform | Status | Notes |
| --- | --- | --- |
| Windows 10/11 | Primary target | Key map follows the active keyboard layout. Focus and Caps Lock guards available. |
| macOS | Supported by PyAutoGUI | Grant your terminal **Accessibility** permission (System Settings → Privacy & Security). No focus or Caps Lock guard. |
| Linux (X11) | Supported by PyAutoGUI | Needs `python3-xlib` and an X display. No focus or Caps Lock guard. |
| Linux (Wayland) | Not supported | Synthetic input is blocked; use an X11 session or XWayland app. |

## Limitations

- **Character set.** Only characters the platform key map can produce are
  typed: in practice printable ASCII plus newline and tab (on Windows, whatever
  the active layout can produce through `VkKeyScan`). Accented letters, emoji,
  smart quotes, arrows and so on are reported as unsupported. PyAutoGUI itself
  would drop them silently; autotype checks first and refuses or reports
  instead.
- **Line endings.** CRLF and CR are converted to LF, so each line break is one
  Enter keystroke. Otherwise Windows files could produce double line breaks on
  some platforms.
- **autotype can't see the target.** It reports keystrokes *sent*. Auto-indent,
  bracket and quote auto-closing, autocomplete, IME input methods, and input
  lag on remote consoles can all change what actually appears. For editors,
  consider `--strip-indent` and turning off auto-closing. For slow consoles,
  raise `--interval`.
- **Tabs** are sent as the Tab key, which may trigger completion in shells or
  indentation in editors. The dry run warns when the file contains tabs.
- **Keyboard layout.** Outside Windows, PyAutoGUI assumes a US layout. On other
  layouts some symbols may come out as different characters.
- **Files** larger than 1 MB, binary files and empty files are rejected.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `PyAutoGUI is not installed` (exit 4) | `python -m pip install -r requirements.txt` with the same Python you use to run the tool. |
| `PyAutoGUI could not start ... graphical desktop session is required` | You're on a headless machine or SSH session without a display. Run it inside the desktop session. On Linux, check `DISPLAY` is set and you're on X11. |
| `input file not found` | The default `solution.txt` is resolved against the **current directory**. `cd` to the project folder or pass the full path. |
| `standard input is not interactive` | You ran it from a script or pipe. Add `--yes`. |
| `the terminal that launched autotype still has keyboard focus` | Click into the target window during the countdown. Use `--countdown 10` for more time. |
| `Caps Lock is on` | Turn Caps Lock off and rerun. |
| `mouse movement detected` | Keep your hands off the mouse while typing runs, or pass `--no-mouse-guard`. |
| Characters reported as unsupported | Replace them (e.g. smart quotes → `'`/`"`), or use `--on-unsupported skip` and fix them by hand afterwards. |
| Indentation doubles up in an editor | Use `--strip-indent`, or turn off auto-indent in the target. |
| Missing or garbled characters on a remote console | Increase `--interval` (e.g. `0.1`–`0.2`). Make sure the remote keyboard layout matches your local one. |
| Nothing happens on macOS | Give the terminal Accessibility permission and restart it. |

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest            # unit + CLI tests
python -m ruff check .      # lint
python -m ruff format --check .
python -m mypy              # strict type checking (config in pyproject.toml)
```

The tests never touch the real desktop. `tests/conftest.py` blocks importing
PyAutoGUI for every test, and the typing logic runs against a recording fake
backend. Subprocess tests only use `--dry-run`. The suite also passes in an
environment with no PyAutoGUI installed.

### Project layout

```text
autotype.py           CLI and all logic (file loading, key-map checks, guards, typing loop)
typer.py              Backward-compatible entry point -> autotype.main()
solution.txt          Default input file (C++ snippet, kept unchanged; see below)
tests/                pytest suite (fake backend; no GUI required)
requirements.txt      Runtime dependency
requirements-dev.txt  Test/lint/type-check tools
pyproject.toml        Tool configuration (pytest, ruff, mypy)
```

## About `solution.txt`

`solution.txt` is the default input and is **kept byte-for-byte unchanged**.
It holds the body of a C++ function (no signature) that works on `tasks` and
`shifts` arrays using prefix sums and `upper_bound`. **The problem statement it
solves isn't in this repository**, so its algorithm hasn't been reviewed or
changed.

When the snippet is wrapped in a guessed signature
(`vector<int> f(vector<int>& tasks, vector<int>& shifts)`) and checked with
`g++ 15.2 -std=c++17 -fsyntax-only`, it **does not compile as written**:

- `vector ans(m);` fails class template argument deduction (a size alone can't
  determine the element type).
- `vector dref = tasks;` and `vector pref(n + 1, 0);` compile through CTAD, but
  `pref` becomes `vector<int>`, while the code stores prefix sums next to
  `long long` totals.

This pattern suggests the template arguments (for example `<long long>` or
`<int>`) were lost when the code was copied, perhaps from a web page that
treated `<...>` as HTML. Restore them from the original source before relying
on the snippet. The file also uses CRLF line endings and no indentation;
autotype handles both (see *Limitations*).
