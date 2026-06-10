#!/usr/bin/env python3
"""Quick calculation checker — works from any working directory.

Usage:
    python C:/Users/polestar/.claude/scripts/check_calc.py <output_file>              # Auto-detect, print summary
    python C:/Users/polestar/.claude/scripts/check_calc.py <output_file> --json       # Machine-readable
    python C:/Users/polestar/.claude/scripts/check_calc.py <output_file> --markdown   # SOP-ready report
    python C:/Users/polestar/.claude/scripts/check_calc.py <output_file> --diagnose   # Full diagnosis
"""

import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure scripts/parsers is importable
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from parsers.runner import main as _main

if __name__ == "__main__":
    _main()
