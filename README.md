# Autotype — Controlled Keystroke-Based Text Input

<div align="center">

### A Local Python Utility for Reliable Text Entry in Desktop Applications

Autotype reads a text file and enters its contents into the focused application, one keystroke at a time, at a steady, configurable rate.

Designed for remote consoles, virtual machines, KVM/noVNC environments, serial-over-web consoles, and technical demonstrations where ordinary clipboard paste is unavailable or unsuitable.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PyAutoGUI](https://img.shields.io/badge/PyAutoGUI-0.9.54%2B-2EA44F?style=flat-square)](https://pyautogui.readthedocs.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-555555?style=flat-square)](#supported-platforms)
[![Testing](https://img.shields.io/badge/Testing-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](#testing-and-development)

**Local execution · Dry-run validation · Configurable typing speed · Built-in safety guards**

[Quick Start](#quick-start) · [Usage](#usage) · [Safety](#safety-and-responsible-use) · [Troubleshooting](#troubleshooting) · [Development](#testing-and-development)

</div>

---

## Overview

**Autotype** is a Python command-line utility that types the contents of a text file into the currently focused desktop application.

It sends keystrokes at a constant, configurable interval rather than attempting to imitate human typing. This makes its behavior predictable and allows the typing speed to be adjusted for different environments.

### Intended use cases

- Entering code or configuration into remote, VM, KVM/noVNC, or serial-over-web consoles where clipboard paste does not work.
- Working in authorized, locked-down environments where paste is disabled by a policy that permits an alternative input method.
- Live technical demonstrations where code or commands need to appear predictably.
- Entering text into desktop applications that accept keyboard input but do not support clipboard insertion.

Autotype deliberately does not attempt to imitate human typing. It must not be used to circumvent paste detection, keystroke analysis, or other integrity controls in exams, assessments, programming contests, or interviews.

### How it works

1. Reads a text file from disk.
2. Validates the file and checks its characters against the platform keyboard mapping.
3. Displays a summary of the input and estimated typing duration.
4. Waits for explicit confirmation unless the permitted non-interactive option is used.
5. Starts a countdown so the user can focus the target application.
6. Sends keystrokes at the configured interval.
7. Reports how many keystrokes were sent if the operation finishes or stops early.

**Important:** Autotype sends real keyboard input to whichever window has focus. It cannot guarantee that the target application will display the text exactly as it appears in the input file.

## Features

| Feature | Description |
|---|---|
| Text-file input | Reads a specified file or defaults to `solution.txt` in the current working directory. |
| Dry-run validation | Checks the input file and reports unsupported characters without typing anything. |
| Configurable typing interval | Sets a fixed delay between keystrokes for faster or slower input. |
| Adjustable countdown | Provides time to focus the target window before typing starts. |
| Keyboard-map validation | Checks supported characters before the first keystroke. |
| Unsupported-character policies | Either abort before typing or skip unsupported characters and report incomplete output. |
| Optional indentation removal | Removes leading spaces and tabs from each line for editors with automatic indentation. |
| Encoding selection | Supports explicit input encodings, including Windows-1252. |
| Mouse-movement guard | Stops typing when the mouse moves beyond the configured guard threshold. |
| PyAutoGUI fail-safe | Retains PyAutoGUI's screen-corner fail-safe. |
| Windows focus protection | Checks terminal focus before typing and stops if focus changes to another window during typing. |
| Windows Caps Lock protection | Refuses to start while Caps Lock is on. |
| Honest completion reporting | Reports the number of keystrokes sent, including when typing stops early. |
| Backward compatibility | `typer.py` remains available as a wrapper around `autotype.py`. |

## Requirements

| Requirement | Version or notes |
|---|---|
| Python | 3.9 or newer; tested on Python 3.13. |
| PyAutoGUI | 0.9.54 or newer. |
| Desktop environment | A graphical desktop session on Windows, macOS, or Linux using X11. |
| Linux dependencies | `python3-xlib` and an available X display when required by PyAutoGUI. |

Autotype requires a usable graphical desktop session. It is not intended to run in a headless environment or an SSH session without an accessible display.

## Quick Start

### 1. Install the dependencies

From the project directory, run:

```bash
python -m pip install -r requirements.txt
```

### 2. Prepare the input file

By default, Autotype reads `solution.txt` from the current working directory.

You can also specify another file:

```bash
python autotype.py commands.txt
```

### 3. Always run a dry run first

```bash
python autotype.py --dry-run solution.txt
```

The dry run validates the file, checks its characters against the platform key map, and prints a report. **It never types anything.**

An illustrative report looks like this:

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

The values above are an example of the report format, not a guarantee about the contents or duration of your current file.

### 4. Type the file into the target application

```bash
python autotype.py solution.txt
```

The normal workflow is:

1. Autotype validates the file and prints a summary.
2. Press Enter to confirm that you want to begin, or type `q` to cancel.
3. A countdown begins. The default is 5 seconds, with a minimum of 3 seconds.
4. During the countdown, click into the target application.
5. Autotype sends the validated keystrokes at the selected interval.
6. A final message reports how many keystrokes were sent.

Keep the target application focused and avoid interacting with the keyboard or mouse while typing is running.

## Installation with a Virtual Environment

Using a virtual environment is recommended to keep project dependencies separate from other Python installations.

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### macOS and Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For development dependencies, including testing, linting, and type checking:

```bash
python -m pip install -r requirements-dev.txt
```

Use the same Python interpreter to install dependencies and run Autotype. This avoids errors caused by installing PyAutoGUI into a different Python environment.

## Usage

The general command syntax is:

```bash
python autotype.py [options] [FILE]
```

`FILE` defaults to `solution.txt` in the current working directory.

The backward-compatible entry point also works:

```bash
python typer.py
```

`typer.py` is a thin wrapper around `autotype.py` and behaves identically.

### Examples

**Run a dry run before typing:**

```bash
python autotype.py --dry-run solution.txt
```

**Type more slowly for a laggy remote console:**

```bash
python autotype.py --interval 0.15 deploy.sh
```

**Use a longer countdown to reach a window on another monitor:**

```bash
python autotype.py --countdown 10 config.yaml
```

**Remove leading indentation for an editor that automatically indents:**

```bash
python autotype.py --strip-indent snippet.py
```

**Skip characters that the keyboard mapping cannot produce:**

```bash
python autotype.py --on-unsupported skip notes.txt
```

This mode may produce incomplete text. Review the final status and repair the missing characters manually.

**Skip the confirmation prompt while retaining the countdown:**

```bash
python autotype.py --yes --countdown 5 commands.txt
```

**Read a Windows-1252 encoded file:**

```bash
python autotype.py --encoding cp1252 legacy.txt
```

## Command-Line Options

| Option | Default | Description |
|---|---|---|
| `FILE` | `solution.txt` | Input text file, resolved relative to the current working directory. |
| `-i`, `--interval SECONDS` | `0.05` | Fixed delay after every keystroke, from 0 to 1 second. |
| `-c`, `--countdown SECONDS` | `5` | Delay before typing begins; accepts whole seconds from 3 to 60. |
| `-y`, `--yes` | Off | Skip the Enter-confirmation prompt. The countdown still runs. |
| `-n`, `--dry-run` | Off | Validate the file and print a report without typing anything. |
| `--on-unsupported {abort,skip}` | `abort` | `abort` refuses to type if any character is unsupported. `skip` types the supported characters and exits with code 6. |
| `--strip-indent` | Off | Remove leading spaces and tabs from every line. |
| `--encoding NAME` | `utf-8` | Select the input encoding. A UTF-8 BOM is always removed. |
| `--no-mouse-guard` | Off | Disable the mouse-movement guard. The corner fail-safe remains active. |
| `-v` | — | Enable debug output. |
| `-q` | — | Show warnings and errors only; also hides countdown messages. |
| `--version` | — | Print the version. |

### Typing interval and duration

The configured interval is the delay after each keystroke.

For a file containing \(N\) characters and an interval \(t\), a rough estimate of the typing-loop duration is:

\[
T \approx N \times t
\]

This estimate excludes startup, countdown, application processing, scheduling delays, and other overhead. Newlines and tabs are input characters that generate their corresponding key events.

A smaller interval may be faster, but it can cause missed or altered input in a laggy remote console. Increase the interval when the target application cannot reliably keep up.

## Safety and Responsible Use

Autotype sends real keystrokes to whichever window has keyboard focus. This makes it useful for applications without clipboard support, but it also means the input target matters.

**Typing a newline sends Enter. In a shell, that can execute a command immediately.** Review command files carefully before typing them into a terminal.

### Built-in protections

**1. Confirmation and countdown**

Nothing is typed before confirmation unless `--yes` is explicitly selected. The countdown still runs, with a minimum of 3 seconds.

Without `--yes`, a non-interactive standard input is refused.

**2. Validation before typing**

File validation and unsupported-character checks happen before the first keystroke. Input errors are reported before typing starts rather than being discovered halfway through the file.

**3. Mouse-movement guard**

Moving the mouse more than 10 pixels from its starting position stops typing immediately. This guard can be disabled using `--no-mouse-guard`, but doing so removes a safety mechanism.

**4. PyAutoGUI corner fail-safe**

PyAutoGUI's fail-safe remains enabled. Moving the mouse into a screen corner stops the operation.

**5. Windows focus guards**

On Windows, Autotype refuses to begin if the terminal that launched it still has focus when the countdown ends. It also stops if keyboard focus moves to a different window during typing.

**6. Windows Caps Lock check**

Autotype refuses to start while Caps Lock is enabled because it can invert the case of letters.

**7. Honest reporting**

If typing stops before completion, the final message reports how many keystrokes were already sent. The target application may therefore contain partial text, which should be inspected before retrying.

### Precautions

- Always run `--dry-run` first.
- Review the entire input file before sending it to a terminal.
- Do not touch the keyboard while Autotype is running. A held Ctrl, Alt, or Windows key can turn ordinary characters into shortcuts.
- Keep your hands off the mouse during typing unless you intend to trigger the guard.
- Remember that Ctrl+C only reaches Autotype while its terminal has focus. Once typing starts in another application, the mouse-based safety mechanisms are usually more useful.
- If the operation stops early, inspect the target before starting again. Retrying the whole file may duplicate text already entered.
- Do not use Autotype to bypass integrity controls in assessments, interviews, or contests.

## Supported Platforms

| Platform | Status | Notes |
|---|---|---|
| Windows 10/11 | Primary target | Keyboard mapping follows the active keyboard layout. Focus and Caps Lock guards are available. |
| macOS | Supported through PyAutoGUI | Grant the terminal Accessibility permission under System Settings → Privacy & Security. No focus or Caps Lock guard is available. |
| Linux (X11) | Supported through PyAutoGUI | Requires `python3-xlib` and an available X display. No focus or Caps Lock guard is available. |
| Linux (Wayland) | Not supported | Synthetic input is blocked in the documented setup. Use an X11 session or an XWayland application where supported. |

Platform behavior depends on the active keyboard layout, desktop permissions, and the target application's input handling.

## Limitations

Autotype validates the characters it can send, but it cannot inspect the final text inside the target application.

### Character set

Only characters supported by the platform keyboard mapping can be typed.

In practice, this is printable ASCII plus newline and tab, subject to the active keyboard layout. On Windows, supported characters are checked through the platform's `VkKeyScan` mapping.

Accented characters, emoji, smart quotes, arrows, and other unsupported symbols are reported before typing begins.

PyAutoGUI may otherwise drop unsupported characters silently, so Autotype validates the input and either refuses to type or applies the selected skip policy.

### Line endings

CRLF and CR line endings are normalized to LF.

Each line break therefore becomes one Enter keystroke, avoiding unintended double line breaks when files created on different platforms are used.

### Target application behavior

Autotype cannot see or verify what the target application actually displays.

The resulting text may differ because of:

- Automatic indentation.
- Automatic bracket or quote closing.
- Autocomplete.
- Input method editors (IMEs).
- Application-specific keyboard shortcuts.
- Input lag in remote consoles.
- Keyboard-layout mismatches.

For editors that automatically indent, consider `--strip-indent` or disabling automatic indentation. For slow remote consoles, increase `--interval`.

### Tabs

Tabs are sent as the Tab key. Depending on the target application, this may trigger shell completion, move focus, or insert indentation.

The dry-run report warns when the input contains tabs.

### Keyboard layout

Outside Windows, PyAutoGUI assumes a US keyboard layout in the documented setup. Symbols may therefore appear differently on non-US layouts.

### File restrictions

Empty files, binary files, files larger than 1 MB, and files that cannot be decoded using the selected encoding are rejected.

## Exit Codes

| Exit code | Meaning |
|---|---|
| `0` | All keystrokes were sent. |
| `1` | Unexpected internal error. Rerun with `-v` for diagnostic output. |
| `2` | Invalid arguments, or `--yes` was not provided when standard input was non-interactive. |
| `3` | Input problem: missing, empty, binary, oversized (over 1 MB), invalid encoding, or unsupported characters with `--on-unsupported abort`. |
| `4` | PyAutoGUI is missing or no usable desktop session is available. |
| `5` | Cancelled at the prompt or stopped by a safety guard or fail-safe. |
| `6` | Typing finished with unsupported characters skipped; the target text is incomplete. |
| `130` | Interrupted with Ctrl+C. |

Exit codes are useful for scripting and automation because they distinguish successful completion from validation errors, missing dependencies, cancellation, and incomplete output.

## Troubleshooting

| Problem | Likely cause and solution |
|---|---|
| `PyAutoGUI is not installed` (exit code 4) | Install dependencies using `python -m pip install -r requirements.txt` with the same Python interpreter used to run Autotype. |
| `PyAutoGUI could not start ... graphical desktop session is required` | Run the utility inside a graphical desktop session. On Linux, verify that `DISPLAY` is set and that the session uses X11. |
| `input file not found` | The default `solution.txt` is resolved against the current working directory. Change to the project directory or pass the file's full path. |
| `standard input is not interactive` | The program was launched from a script or pipe. Use `--yes` if non-interactive execution is appropriate; the countdown remains active. |
| `the terminal that launched autotype still has keyboard focus` | Click the target application during the countdown. Increase the countdown with `--countdown 10` if necessary. |
| `Caps Lock is on` | Disable Caps Lock and rerun. |
| `mouse movement detected` | Keep the mouse still during typing or use `--no-mouse-guard` when disabling that protection is appropriate. |
| Characters reported as unsupported | Replace unsupported symbols with supported characters, such as replacing smart quotes with ordinary quotes, or use `--on-unsupported skip` and repair the output manually. |
| Indentation is duplicated in an editor | Use `--strip-indent` or disable the editor's automatic indentation. |
| Missing or garbled characters in a remote console | Increase the interval, for example to `0.1`–`0.2` seconds. Verify that the remote and local keyboard layouts match. |
| Nothing happens on macOS | Grant the terminal Accessibility permission under System Settings → Privacy & Security, then restart the terminal. |

### Python environment problems

If Autotype reports that PyAutoGUI is missing even after installation, check which Python interpreter is being used:

```bash
python --version
python -m pip --version
python -m pip show pyautogui
```

If the package was installed into a different environment, activate the intended virtual environment and reinstall the dependencies.

### Remote-console input problems

Remote consoles may process input more slowly than local applications.

Try a slower interval:

```bash
python autotype.py --interval 0.15 commands.txt
```

Run a dry run first and verify the keyboard layout before sending the input.

## Testing and Development

Install the development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the test suite:

```bash
python -m pytest
```

Run linting:

```bash
python -m ruff check .
```

Check formatting:

```bash
python -m ruff format --check .
```

Run strict type checking:

```bash
python -m mypy
```

The type-checking configuration is maintained in `pyproject.toml`.

### Test design

The tests are deliberately designed not to interact with the real desktop.

- `tests/conftest.py` blocks importing PyAutoGUI during tests.
- Typing logic runs against a recording fake backend.
- Subprocess tests use `--dry-run`.
- The test suite also runs in environments where PyAutoGUI is not installed.

This makes it possible to validate the typing logic, CLI behavior, validation rules, and safety-related control flow without sending real keystrokes or requiring a graphical desktop.

## Project Structure

```text
.
├── autotype.py             # CLI and core logic:
│                           # file loading, key-map checks, guards, typing loop
├── typer.py                # Backward-compatible entry point
├── solution.txt            # Default input file; preserved unchanged
├── tests/                  # pytest suite using a fake backend
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Testing, linting and type-checking tools
└── pyproject.toml          # pytest, Ruff and mypy configuration
```

## About `solution.txt`

`solution.txt` is the default input file and is **kept byte-for-byte unchanged**.

It contains the body of a C++ function, without a function signature, that operates on `tasks` and `shifts` arrays using prefix sums and `upper_bound`.

The problem statement that this snippet solves is not included in the repository. Therefore, the algorithm itself has not been reviewed or changed as part of the Autotype project.

### Compilation caveat

When the snippet is wrapped in the guessed signature:

```cpp
vector<int> f(vector<int>& tasks, vector<int>& shifts)
```

and checked with `g++ 15.2 -std=c++17 -fsyntax-only`, it does not compile as written.

The reported issues are:

- `vector ans(m);` fails class template argument deduction because a size alone does not determine the vector's element type.
- `vector dref = tasks;` and `vector pref(n + 1, 0);` compile through class template argument deduction, but `pref` becomes `vector<int>` even though the code stores prefix sums alongside `long long` totals.

This pattern suggests that template arguments, such as `<long long>` or `<int>`, may have been lost when the code was copied from a source that interpreted angle brackets as HTML.

Restore the template arguments from the original source before relying on the snippet.

The file also uses CRLF line endings and contains no indentation. Autotype handles the line endings by normalizing them to LF; `--strip-indent` is available when leading indentation needs to be removed from other input files.

## Responsible Use

Autotype is a general-purpose local input utility. Its intended role is to help users enter text into applications where ordinary paste is unavailable or unsuitable.

Use it only in environments where you are authorized to automate keyboard input. Respect the rules of the target application and any applicable institutional, workplace, or assessment policies.

Do not use the tool to evade integrity controls, conceal prohibited assistance, or misrepresent how work was produced.

## Summary

Autotype provides a predictable, configurable way to enter text into a focused desktop application, with validation before typing and safeguards designed to reduce accidental input.

Its core workflow is straightforward:

**Validate → Confirm → Countdown → Type → Report**

The dry-run mode, explicit confirmation, keyboard-map validation, configurable interval, mouse guard, platform-specific checks, and test suite help make the behavior easier to understand and control.

---

<div align="center">

### Autotype

**Predictable input. Explicit safeguards. Transparent execution.**

A lightweight Python utility for controlled text entry in local desktop environments and remote consoles.

</div>
