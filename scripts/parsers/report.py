"""Generate structured reports from parse results.

Provides JSON and human-readable text reports suitable for
SOP integration or direct delivery to clients.
"""

import json
from .base import ParseResult, ConvergenceStatus


def to_json(result: ParseResult, indent: int = 2) -> str:
    """Serialize ParseResult to JSON string."""
    data = {
        "code": result.code,
        "file_path": result.file_path,
        "success": result.success,
        "errors": result.errors,
        "warnings": result.warnings[:10],  # cap
        "scf": {
            "cycles_completed": len(result.scf_cycles),
            "converged": result.scf_converged,
            "status": result.scf_status.value,
            "cycles_remaining": result.scf_cycles_remaining,
            "time_remaining_seconds": result.scf_time_remaining_seconds,
            "avg_time_per_scf": result.avg_time_per_scf,
            "energy_history": [
                {"cycle": c.cycle, "energy": c.energy, "delta_e": c.delta_e}
                for c in result.scf_cycles[-10:]  # last 10 only
            ],
        },
        "geometry": {
            "steps_completed": len(result.geo_steps),
            "converged": result.geo_converged,
            "steps_remaining": result.geo_steps_remaining,
            "time_remaining_seconds": result.geo_time_remaining_seconds,
            "force_history": [
                {
                    "step": s.step,
                    "energy": s.energy,
                    "rms_force": s.rms_force,
                    "max_force": s.max_force,
                }
                for s in result.geo_steps[-5:]  # last 5 only
            ] if result.geo_steps else [],
        },
        "final_energy": result.final_energy,
        "final_energy_units": result.final_energy_units,
        "elapsed_time_seconds": result.elapsed_time_seconds,
        "metadata": {k: v for k, v in result.raw_headers.items()
                      if not isinstance(v, (list, dict))},
    }
    return json.dumps(data, indent=indent, ensure_ascii=False)


def to_markdown(result: ParseResult) -> str:
    """Generate a markdown report suitable for client delivery or SOP."""
    lines = []
    lines.append(f"# {result.code.upper()} Calculation Report")
    lines.append(f"**File**: `{result.file_path}`")
    lines.append(f"**Status**: {'SUCCESS' if result.success else 'FAILURE / INCOMPLETE'}")
    lines.append("")

    # SCF Section
    if result.scf_cycles:
        lines.append("## SCF Convergence")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Cycles completed | {len(result.scf_cycles)} |")
        lines.append(f"| Status | **{result.scf_status.value.upper()}** |")
        lines.append(f"| Converged | {'Yes' if result.scf_converged else 'No'} |")
        if result.final_energy is not None:
            lines.append(f"| Current Energy | {result.final_energy:.8f} {result.final_energy_units} |")
        if result.avg_time_per_scf:
            lines.append(f"| Avg Time/Cycle | {_fmt_time(result.avg_time_per_scf)} |")
        if result.scf_cycles_remaining is not None:
            lines.append(f"| Est. Cycles Remaining | {result.scf_cycles_remaining} |")
        if result.scf_time_remaining_seconds is not None:
            lines.append(f"| Est. Time Remaining | {_fmt_time(result.scf_time_remaining_seconds)} |")
        lines.append("")

        # Energy trend
        lines.append("### Energy Trend (last 10 cycles)")
        lines.append("| Cycle | Energy (Hartree) | Delta E |")
        lines.append("|-------|-----------------|---------|")
        for c in result.scf_cycles[-10:]:
            de_str = f"{c.delta_e:.2e}" if c.delta_e is not None else "-"
            lines.append(f"| {c.cycle} | {c.energy:.10f} | {de_str} |")
        lines.append("")

    # Geometry Optimization Section
    if result.geo_steps:
        lines.append("## Geometry Optimization")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Steps completed | {len(result.geo_steps)} |")
        s = result.geo_steps[-1]
        lines.append(f"| Converged | {'Yes' if result.geo_converged else 'No'} |")
        if s.rms_force is not None:
            lines.append(f"| RMS Force (current) | {s.rms_force:.6f} |")
        if s.max_force is not None:
            lines.append(f"| Max Force (current) | {s.max_force:.6f} |")
        if result.geo_steps_remaining is not None:
            lines.append(f"| Est. Steps Remaining | {result.geo_steps_remaining} |")
        lines.append("")

    # Errors and Warnings
    if result.errors:
        lines.append("## Errors")
        for e in result.errors:
            lines.append(f"- [ERROR] {e}")
        lines.append("")

    if result.warnings:
        lines.append("## Warnings")
        for w in result.warnings[:10]:
            lines.append(f"- [WARN] {w}")
        lines.append("")

    # Timing
    if result.elapsed_time_seconds is not None:
        lines.append("## Timing")
        lines.append(f"- Elapsed: {_fmt_time(result.elapsed_time_seconds)}")
        lines.append("")

    return "\n".join(lines)


def to_sop_entry(result: ParseResult, client: str = "", task: str = "") -> str:
    """Generate a minimal SOP entry from parse results.

    Designed to be appended to the user's SOP collection.
    """
    lines = []
    lines.append(f"## {result.code.upper()} | {task or 'Task'} | {client or 'Client'}")
    lines.append(f"- Date: auto")
    lines.append(f"- Status: {'PASS' if result.success else 'FAIL'}")
    lines.append(f"- Energy: {result.final_energy:.8f} {result.final_energy_units}" if result.final_energy else "- Energy: N/A")
    lines.append(f"- SCF cycles: {len(result.scf_cycles)}, Status: {result.scf_status.value}")
    lines.append(f"- Geo steps: {len(result.geo_steps)}, Converged: {result.geo_converged}")
    if result.errors:
        lines.append(f"- Errors: {'; '.join(result.errors[:3])}")
    if result.warnings:
        lines.append(f"- Warnings: {'; '.join(result.warnings[:3])}")
    lines.append("")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"
