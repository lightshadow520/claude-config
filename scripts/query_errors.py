#!/usr/bin/env python3
"""
Structured error knowledge base query tool.
Replaces grep-based search of diagnostics.md with precise JSON queries.

Usage:
  python query_errors.py --type oom_killed              # by error type
  python query_errors.py --code vasp                     # all errors for a code
  python query_errors.py --type scf_diverged --code vasp # intersection
  python query_errors.py --search "X11"                  # keyword search
  python query_errors.py --severity critical             # filter by severity
  python query_errors.py --suggest --type oom_killed --code vasp  # fix suggestions
  python query_errors.py --list-types                    # list all error types
  python query_errors.py --json                          # output as JSON for Agent
"""
import argparse
import json
import os
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "comp-chem" / "error_db.json"


def load_db():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def search_errors(db, query):
    """Search across all text fields in errors."""
    results = []
    q = query.lower()
    for err in db["errors"]:
        score = 0
        fields = []
        # Search in symptoms
        for s in err.get("symptoms", []):
            if q in s.lower():
                score += 2
                fields.append(f"symptom: {s[:80]}")
        # Search in root causes
        for rc in err.get("root_causes", []):
            if q in rc["cause"].lower():
                score += 3
                fields.append(f"root_cause: {rc['cause'][:80]}")
        # Search in fixes
        for fix in err.get("fixes", []):
            if q in fix["action"].lower():
                score += 2
                fields.append(f"fix: {fix['action'][:80]}")
            if q in fix.get("side_effects", "").lower():
                score += 1
        # Search in error_type and description
        if q in err["error_type"].lower():
            score += 5
            fields.append(f"error_type match")
        if score > 0:
            err["_score"] = score
            err["_match_fields"] = fields[:5]
            results.append(err)
    return sorted(results, key=lambda x: x["_score"], reverse=True)


def get_fixes(db, error_type=None, code=None, min_confidence="MEDIUM"):
    """Get fix suggestions, optionally filtered."""
    confidence_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    all_fixes = []

    for err in db["errors"]:
        if error_type and err["error_type"] != error_type:
            continue
        for fix in err["fixes"]:
            if code and code not in fix.get("applies_to", []):
                continue
            if confidence_order.get(fix.get("confidence", "LOW"), 0) < confidence_order.get(min_confidence, 0):
                continue
            all_fixes.append({
                "error_type": err["error_type"],
                "action": fix["action"],
                "params": fix.get("params", {}),
                "confidence": fix.get("confidence"),
                "applies_to": fix.get("applies_to", []),
                "side_effects": fix.get("side_effects", ""),
                "validation": fix.get("validation", ""),
            })

    all_fixes.sort(key=lambda x: confidence_order.get(x["confidence"], 0), reverse=True)
    return all_fixes


def format_fixes(fixes):
    """Pretty-print fix suggestions."""
    out = []
    C = "\033[1;36m"  # cyan
    G = "\033[1;32m"  # green
    Y = "\033[1;33m"  # yellow
    R = "\033[1;31m"  # red
    X = "\033[0m"     # reset

    for i, fix in enumerate(fixes):
        conf_color = {"HIGH": G, "MEDIUM": Y, "LOW": R}.get(fix["confidence"], X)
        out.append(f"  {C}[{i+1}]{X} {fix['action']}")
        out.append(f"      Error: {fix['error_type']}  |  Confidence: {conf_color}{fix['confidence']}{X}  |  Code: {', '.join(fix['applies_to'])}")
        if fix["params"]:
            params_str = ", ".join(f"{k}={v}" for k, v in fix["params"].items())
            out.append(f"      Params: {params_str}")
        if fix["side_effects"]:
            out.append(f"      Side effects: {fix['side_effects']}")
        if fix["validation"]:
            out.append(f"      Validation: {fix['validation']}")
        out.append("")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="Structured error knowledge base query")
    p.add_argument("--type", help="Filter by error_type (e.g. oom_killed, scf_diverged)")
    p.add_argument("--code", help="Filter by code (vasp, cp2k, lammps, gaussian, orca, qe, castep)")
    p.add_argument("--severity", choices=["critical", "warning", "info"], help="Filter by severity")
    p.add_argument("--search", help="Keyword search across all fields")
    p.add_argument("--suggest", action="store_true", help="Output fix suggestions (use with --type/--code)")
    p.add_argument("--min-confidence", default="MEDIUM", choices=["HIGH", "MEDIUM", "LOW"])
    p.add_argument("--list-types", action="store_true", help="List all known error types")
    p.add_argument("--list-codes", action="store_true", help="List all supported codes")
    p.add_argument("--json", action="store_true", help="Output as JSON (for Agent consumption)")
    args = p.parse_args()

    db = load_db()

    # List modes
    if args.list_types:
        for err in db["errors"]:
            print(f"  {err['error_type']:<25} [{err['severity']}] {len(err['symptoms'])} symptoms, {len(err['fixes'])} fixes")
        sys.exit(0)

    if args.list_codes:
        for code, info in db["code_specific_patterns"].items():
            print(f"  {code:<12} common: {', '.join(info['common_errors'][:5])}")
        sys.exit(0)

    # Main query
    results = db["errors"]

    if args.type:
        results = [e for e in results if e["error_type"] == args.type]

    if args.code:
        results = [e for e in results if any(args.code in fix.get("applies_to", []) for fix in e.get("fixes", []))]

    if args.severity:
        results = [e for e in results if e["severity"] == args.severity]

    if args.search:
        results = search_errors(db, args.search)

    # Output
    if args.suggest:
        fixes = get_fixes(db, args.type, args.code, args.min_confidence)
        if args.json:
            print(json.dumps(fixes, ensure_ascii=False, indent=2))
        else:
            if not fixes:
                print("No matching fixes found.")
            else:
                print(f"\n  Found {len(fixes)} fix suggestion(s):\n")
                print(format_fixes(fixes))
    elif args.json:
        # Strip internal fields
        clean = []
        for r in results:
            c = {k: v for k, v in r.items() if not k.startswith("_")}
            clean.append(c)
        out = {
            "query": {"type": args.type, "code": args.code, "severity": args.severity, "search": args.search},
            "count": len(clean),
            "results": clean,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("No matching errors found.")
            sys.exit(0)

        for i, err in enumerate(results):
            sev_color = {"critical": "\033[1;31m", "warning": "\033[1;33m", "info": "\033[0m"}.get(err["severity"], "")
            sev_reset = "\033[0m" if sev_color else ""
            print(f"\n  ── {sev_color}[{err['error_type']}]{sev_reset} ({err['severity']}) ──")
            print(f"  Symptoms ({len(err['symptoms'])}):")
            for s in err["symptoms"][:3]:
                print(f"    • {s}")
            print(f"  Root Causes:")
            for rc in err["root_causes"][:3]:
                print(f"    • [{rc['likelihood']}] {rc['cause']}")
            print(f"  Fixes ({len(err['fixes'])}):")
            for fix in err["fixes"][:3]:
                print(f"    • [{fix['confidence']}] {fix['action']} ({', '.join(fix.get('applies_to', []))})")
            if "_match_fields" in err:
                print(f"  Match: {' | '.join(err['_match_fields'])}")


if __name__ == "__main__":
    main()
