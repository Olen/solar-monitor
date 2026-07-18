#!/usr/bin/env python3
"""Entry point shim. Real logic lives in the importable monitor_app module."""
import sys

from monitor_app import main

if __name__ == "__main__":
    sys.exit(main())
