"""Computational Chemistry Output Parsers.

Auto-detects code type and extracts:
- SCF energy convergence history
- Geometry optimization progress
- Timing information & ETA
- Error/warning patterns

Usage:
    python scripts/check_calc.py <output_file>
    python scripts/parsers/runner.py <output_file> [--json] [--plot] [--diagnose]
"""

from .runner import detect_code

__all__ = [
    "detect_code",
]
