#!/usr/bin/env python3
"""Entry-point shim: python -m leadforge"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
