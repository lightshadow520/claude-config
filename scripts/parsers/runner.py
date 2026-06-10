#!/usr/bin/env python3
"""Unified runner for computational chemistry output parsing.

Usage:
    python scripts/parsers/runner.py <output_file>         # auto-detect, print text summary
    python scripts/parsers/runner.py <output_file> --json  # JSON output
    python scripts/parsers/runner.py <output_file> --markdown  # Markdown report
    python scripts/parsers/runner.py <output_file> --sop   # SOP snippet
    python scripts/parsers/runner.py <output_file> --diagnose  # Run diagnosis
"""

import sys
import json
import os


def detect_code(file_path: str, content: str = None) -> str:
    """Auto-detect which code produced this output file.

    Checks file naming conventions and content signatures.
    """
    basename = os.path.basename(file_path).lower()

    # Check filename-based detection first
    if basename.endswith(".log") or basename.endswith(".gjf") or "gaussian" in basename.lower():
        # Could be Gaussian or CP2K or other — check content
        pass
    if basename == "outcar" or "outcar" in basename:
        return "vasp"
    if basename == "oszicar" or "oszicar" in basename:
        return "vasp"
    if basename.endswith(".out") and ("orca" in basename.lower() or basename.startswith("orca")):
        return "orca"
    if basename.startswith("cp2k") or "cp2k" in basename.lower():
        return "cp2k"
    if basename.startswith("log.lammps") or "lammps" in basename.lower():
        return "lammps"
    if basename.endswith(".edr") or basename.endswith(".trr"):
        return "gromacs"
    if basename.endswith(".mdlog") or "gromacs" in basename.lower():
        return "gromacs"
    if basename.endswith(".mdout") or "amber" in basename.lower():
        return "amber"
    if basename.endswith(".castep"):
        return "ms"
    if basename.endswith(".outmol"):
        return "ms"
    if basename.startswith("lcurve") or basename.endswith(".pt"):
        return "ml"
    if any(kw in basename for kw in ["model.ckpt", "deepmd", "nequip", "mace", "chgnet", "m3gnet"]):
        return "ml"

    # Load content for deeper inspection if not already provided
    if content is None:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(10000)  # first 10KB
        except (FileNotFoundError, PermissionError):
            return "unknown"

    # Content-based detection
    content_lower = content.lower()
    first_line = content.split("\n")[0] if content else ""

    # Gaussian: starts with " Entering Gaussian System" or "Gaussian" or # route
    if "gaussian" in first_line.lower() or "entering gaussian" in content_lower[:200]:
        return "gaussian"
    if first_line.strip().startswith("#") and ("p " in first_line[:10] or "n " in first_line[:10]):
        # #p or #n route section = Gaussian
        if "rb3lyp" in first_line.lower() or "hf/" in first_line.lower() or "mp2/" in first_line.lower():
            return "gaussian"

    # VASP: OUTCAR starts with " vasp."
    if first_line.strip().startswith("vasp.") or "vasp" in first_line[:10]:
        return "vasp"
    if "running on" in content_lower[:500] and "vasp" in content_lower[:500]:
        return "vasp"

    # ORCA: starts with "* O   R   C   A *" or "*** O   R   C   A ***"
    if "o   r   c   a" in first_line.lower() or "* o r c a" in content_lower[:200]:
        return "orca"
    if "orca" in first_line.lower():
        return "orca"

    # CP2K: starts with " DBCSR|" or "CP2K|"
    if "cp2k" in first_line.lower() or "dbcsr" in first_line.lower():
        return "cp2k"

    # LAMMPS
    if "lammps" in content_lower[:500]:
        return "lammps"

    # GROMACS
    if "gromacs" in content_lower[:500] or ":-)  g  r  o  m  a  c  s" in content_lower[:500]:
        return "gromacs"

    # AMBER
    if "amber" in content_lower[:500] or "sander" in content_lower[:500] or "pmemd" in content_lower[:500]:
        return "amber"

    # Materials Studio / CASTEP
    if "castep" in content_lower[:500] or "materials studio" in content_lower[:500]:
        return "ms"
    if "dmol3" in first_line.lower() or "dmol3" in content_lower[:200]:
        return "ms"

    # ML potentials
    if any(kw in content_lower[:500] for kw in ["deepmd", "model.ckpt", "mace", "nequip",
                                                  "chgnet", "m3gnet", "asap", "lcurve"]):
        return "ml"
    if first_line.strip().startswith("#") and ("step" in first_line.lower()):
        # Could be lcurve.out
        if "rmse" in first_line.lower():
            return "ml"

    # Fallback: try to guess from any recognizable pattern
    if "scf done" in content_lower:
        return "gaussian"
    if "free energ" in content_lower or "toten" in content_lower:
        return "vasp"
    if "final single point energy" in content_lower:
        return "orca"

    return "unknown"


def _get_parser(code):
    """Lazy-load parser module. Uses importlib for reliability."""
    from importlib import import_module

    module_map = {
        "gaussian": "parsers.gaussian",
        "vasp": "parsers.vasp",
        "orca": "parsers.orca",
        "cp2k": "parsers.cp2k",
        "lammps": "parsers.lammps",
        "gromacs": "parsers.gromacs",
        "amber": "parsers.amber",
        "ms": "parsers.materials_studio",
        "ml": "parsers.ml_potentials",
    }

    class_map = {
        "gaussian": "GaussianParser", "vasp": "VASPParser", "orca": "ORCAParser",
        "cp2k": "CP2KParser", "lammps": "LAMMPSParser", "gromacs": "GROMACSParser",
        "amber": "AMBERParser", "ms": "MaterialsStudioParser", "ml": "MLPotentialParser",
    }

    mod_name = module_map.get(code, "parsers.gaussian")
    cls_name = class_map.get(code, "GaussianParser")

    mod = import_module(mod_name)
    return getattr(mod, cls_name)()


def detect_and_parse(file_path: str):
    """High-level API: detect code type and parse in one call.

    Returns ParseResult.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(10000)

    code = detect_code(file_path, content)
    if code == "unknown":
        code = "gaussian"

    parser = _get_parser(code)
    return parser.parse(file_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python runner.py <output_file> [--json|--markdown|--sop|--diagnose]")
        sys.exit(1)

    file_path = sys.argv[1]
    flags = [a for a in sys.argv[2:] if a.startswith("--")]

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Load content for detection
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(10000)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    code = detect_code(file_path, content)

    if code == "unknown":
        print(f"Warning: Cannot identify code type for '{file_path}'.")
        print("Try forcing with --code flag. Falling back to Gaussian parser.")
        code = "gaussian"

    parser = _get_parser(code)
    result = parser.parse(file_path)

    # Summary from the base parser
    summary = parser.generate_summary(result)

    # Output based on flags
    if "--json" in flags:
        from .report import to_json
        print(to_json(result))
    elif "--markdown" in flags:
        from .report import to_markdown
        print(to_markdown(result))
    elif "--sop" in flags:
        from .report import to_sop_entry
        print(to_sop_entry(result))
    elif "--diagnose" in flags:
        import importlib
        diagnose_mod = importlib.import_module("parsers.diagnose")

        print(summary)
        print("\n=== DIAGNOSIS ===")

        # Full content for diagnosis
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            full_content = f.read()

        diag_results = diagnose_mod.diagnose_error(full_content, code)
        if diag_results:
            for d in diag_results:
                print(f"\n[{d.confidence.upper()} confidence] {d.issue}")
                print(f"  Evidence: {d.evidence}")
                print(f"  Fix: {d.fix}")

        if result.scf_cycles:
            scf_diag = diagnose_mod.diagnose_scf_oscillation(result.scf_cycles)
            for d in scf_diag:
                print(f"\n[{d.confidence.upper()} confidence] {d.issue}")
                print(f"  Evidence: {d.evidence}")
                print(f"  Fix: {d.fix}")

        if result.geo_steps:
            geo_diag = diagnose_mod.diagnose_geo_optimization_failure(full_content, result.geo_steps)
            for d in geo_diag:
                print(f"\n[{d.confidence.upper()} confidence] {d.issue}")
                print(f"  Evidence: {d.evidence}")
                print(f"  Fix: {d.fix}")
    else:
        print(summary)


if __name__ == "__main__":
    main()
