import sys

import pytest


@pytest.fixture(autouse=True)
def _block_real_pyautogui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make importing the real PyAutoGUI fail, so no test can ever send
    keystrokes to the desktop or require a GUI session."""
    monkeypatch.setitem(sys.modules, "pyautogui", None)
