#!/usr/bin/env python3
"""Entry-point shim: python -m arizona_leads"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
