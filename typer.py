"""Compatibility entry point: ``python typer.py [options] [FILE]``.

All logic lives in autotype.py; run ``python autotype.py --help`` for usage.
"""

import sys

from autotype import main

if __name__ == "__main__":
    sys.exit(main())
