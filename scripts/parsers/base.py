"""Base classes for computational chemistry output parsers."""

import re
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ConvergenceStatus(Enum):
    CONVERGED = "converged"
    CONVERGING = "converging"
    OSCILLATING = "oscillating"
    DIVERGING = "diverging"
    STUCK = "stuck"
    UNKNOWN = "unknown"


@dataclass
class SCFCycle:
    """Single SCF iteration."""
    cycle: int
    energy: float  # in Hartree or eV
    delta_e: Optional[float] = None  # |E_i - E_{i-1}|
    rms_density: Optional[float] = None
    max_density: Optional[float] = None
    time_seconds: Optional[float] = None


@dataclass
class GeoStep:
    """Single geometry optimization step."""
    step: int
    energy: float
    delta_e: Optional[float] = None
    rms_force: Optional[float] = None
    max_force: Optional[float] = None
    rms_displacement: Optional[float] = None
    max_displacement: Optional[float] = None
    converged: bool = False


@dataclass
class ParseResult:
    """Unified parse result for any code."""
    code: str  # 'gaussian', 'vasp', 'orca', 'cp2k', 'lammps', 'gromacs', 'amber', 'ms', 'ml'
    file_path: str
    success: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    # SCF convergence
    scf_cycles: list = field(default_factory=list)  # list of SCFCycle
    scf_converged: bool = False
    scf_status: ConvergenceStatus = ConvergenceStatus.UNKNOWN
    scf_cycles_remaining: Optional[int] = None  # estimated cycles to convergence
    scf_time_remaining_seconds: Optional[float] = None

    # Geometry optimization
    geo_steps: list = field(default_factory=list)  # list of GeoStep
    geo_converged: bool = False
    geo_steps_remaining: Optional[int] = None
    geo_time_remaining_seconds: Optional[float] = None

    # Timing
    avg_time_per_scf: Optional[float] = None  # seconds
    avg_time_per_geo_step: Optional[float] = None
    elapsed_time_seconds: Optional[float] = None
    total_estimated_time_seconds: Optional[float] = None

    # Final results (if calculation complete)
    final_energy: Optional[float] = None
    final_energy_units: str = "Hartree"

    # Raw metadata
    raw_headers: dict = field(default_factory=dict)
    raw_summary: str = ""


class BaseParser:
    """Base parser with convergence analysis."""

    code = "unknown"
    scf_convergence_threshold: float = 1e-8  # default for energy-based codes

    def parse(self, file_path: str) -> ParseResult:
        raise NotImplementedError

    def _extract_float(self, text: str, pattern: str, group: int = 0) -> Optional[float]:
        """Extract a float from text using regex."""
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(group) if group else m.group())
            except (ValueError, IndexError):
                return None
        return None

    def _extract_all_floats(self, text: str, pattern: str) -> list[float]:
        """Extract all matching floats."""
        return [float(x) for x in re.findall(pattern, text) if x]

    def analyze_scf_convergence(self, cycles: list) -> dict:
        """Analyze SCF convergence trend.

        Uses exponential fit to log(dE) to estimate remaining cycles.
        Handles oscillating and stuck behavior detection.
        """
        if len(cycles) < 3:
            return {
                "status": ConvergenceStatus.UNKNOWN,
                "cycles_remaining": None,
                "time_remaining": None,
                "trend": "insufficient_data",
            }

        # Calculate delta E
        deltas = []
        for i in range(1, len(cycles)):
            de = abs(cycles[i].energy - cycles[i - 1].energy)
            deltas.append(de)

        recent_deltas = deltas[-5:] if len(deltas) >= 5 else deltas
        avg_recent_de = sum(recent_deltas) / len(recent_deltas)
        max_de = max(abs(d) for d in deltas)

        # Detect oscillation: sign changes in energy difference
        signs = 0
        for i in range(2, len(cycles)):
            d1 = cycles[i].energy - cycles[i - 1].energy
            d2 = cycles[i - 1].energy - cycles[i - 2].energy
            if d1 * d2 < 0:
                signs += 1
        oscillation_ratio = signs / max(len(cycles) - 2, 1)

        # Detect divergence
        if len(deltas) >= 4:
            first_half = sum(abs(d) for d in deltas[:len(deltas) // 2]) / max(len(deltas) // 2, 1)
            second_half = sum(abs(d) for d in deltas[len(deltas) // 2:]) / max(len(deltas) - len(deltas) // 2, 1)
            is_diverging = second_half > first_half * 2 and avg_recent_de > 1e-4
        else:
            is_diverging = False

        # Detect stuck
        if len(recent_deltas) >= 3:
            is_stuck = all(d < 1e-7 for d in recent_deltas) and not any(
                abs(cycles[i].energy - cycles[i - 1].energy) > 1e-6 for i in range(-5, 0) if i != 0
            )
        else:
            is_stuck = False

        # Status
        if is_diverging and avg_recent_de > 1e-3:
            status = ConvergenceStatus.DIVERGING
        elif oscillation_ratio > 0.5 and avg_recent_de > 1e-5:
            status = ConvergenceStatus.OSCILLATING
        elif is_stuck:
            status = ConvergenceStatus.STUCK
        elif avg_recent_de < 1e-10:
            status = ConvergenceStatus.CONVERGED
        else:
            status = ConvergenceStatus.CONVERGING

        # Estimate remaining cycles
        cycles_remaining = None
        if status == ConvergenceStatus.CONVERGING and len(deltas) >= 5:
            # Log-linear extrapolation
            # Fit: log10(dE_i) = a * i + b
            try:
                log_deltas = []
                for i, d in enumerate(deltas[-10:]):
                    if d > 0:
                        log_deltas.append((i + len(deltas) - min(10, len(deltas)), math.log10(d)))

                if len(log_deltas) >= 4:
                    n = len(log_deltas)
                    sum_x = sum(p[0] for p in log_deltas)
                    sum_y = sum(p[1] for p in log_deltas)
                    sum_xy = sum(p[0] * p[1] for p in log_deltas)
                    sum_x2 = sum(p[0] ** 2 for p in log_deltas)

                    denominator = n * sum_x2 - sum_x ** 2
                    if abs(denominator) > 1e-15:
                        slope = (n * sum_xy - sum_x * sum_y) / denominator

                        if slope < 0:  # energy differences are shrinking
                            target_log = math.log10(1e-8)  # target convergence
                            current_log = log_deltas[-1][1]
                            if slope < -1e-15:
                                steps_to_target = (target_log - current_log) / slope
                                # steps_to_target is from the last point in log_deltas
                                cycles_remaining = max(0, int(math.ceil(steps_to_target)))
            except (ValueError, OverflowError):
                cycles_remaining = None

        # Time estimate
        time_remaining = None
        if cycles_remaining is not None and cycles:
            times = [c.time_seconds for c in cycles if c.time_seconds]
            if times:
                avg_time = sum(times) / len(times)
                time_remaining = cycles_remaining * avg_time

        return {
            "status": status,
            "cycles_remaining": cycles_remaining,
            "time_remaining": time_remaining,
            "avg_recent_de": avg_recent_de,
            "oscillation_ratio": oscillation_ratio,
            "is_diverging": is_diverging,
            "trend_description": self._describe_trend(status, cycles_remaining, avg_recent_de, oscillation_ratio),
        }

    def _describe_trend(self, status, cycles_remaining, avg_de, osc_ratio):
        """Human-readable trend description."""
        if status == ConvergenceStatus.CONVERGED:
            return "Energy has converged"
        elif status == ConvergenceStatus.DIVERGING:
            return f"Energy is DIVERGING — recent dE ≈ {avg_de:.1e}. Check initial geometry or SCF settings."
        elif status == ConvergenceStatus.OSCILLATING:
            return f"Energy is OSCILLATING (oscillation ratio {osc_ratio:.0%}). Consider damping/mixing adjustments."
        elif status == ConvergenceStatus.STUCK:
            return "Energy is STUCK — dE near zero across many cycles but not formally converged."
        elif status == ConvergenceStatus.CONVERGING:
            if cycles_remaining is not None:
                return f"Converging steadily — estimated {cycles_remaining} more cycles ({avg_de:.1e} → target)"
            else:
                return f"Converging — recent dE ≈ {avg_de:.1e}, cannot reliably estimate remaining cycles"
        return "Insufficient data to determine trend"

    def analyze_geo_convergence(self, steps: list) -> dict:
        """Analyze geometry optimization convergence trend."""
        if not steps:
            return {"status": ConvergenceStatus.UNKNOWN, "steps_remaining": None, "trend": "no_steps"}

        last = steps[-1]
        if last.converged:
            return {"status": ConvergenceStatus.CONVERGED, "steps_remaining": 0, "trend": "Optimization converged"}

        # Check if forces are trending down
        forces = [s.rms_force for s in steps if s.rms_force is not None]
        if len(forces) >= 3:
            recent = forces[-3:]
            if all(f is not None for f in recent):
                if recent[-1] < recent[-2] < recent[-3]:
                    # Decreasing forces
                    # Linear extrapolation
                    indices = list(range(len(forces) - 3, len(forces)))
                    avg_reduction = (recent[0] - recent[-1]) / 3
                    if avg_reduction > 0 and recent[-1] > 1e-5:
                        steps_to_target = recent[-1] / avg_reduction / 2  # conservative estimate
                        remaining = max(0, int(math.ceil(steps_to_target)))
                        return {
                            "status": ConvergenceStatus.CONVERGING,
                            "steps_remaining": remaining,
                            "trend": f"Forces decreasing — ~{remaining} more steps estimated",
                        }

        # Check for divergence
        if len(forces) >= 4:
            first_half = sum(forces[:len(forces) // 2]) / max(len(forces) // 2, 1)
            second_half = sum(forces[len(forces) // 2:]) / max(len(forces) - len(forces) // 2, 1)
            if second_half > first_half * 1.5:
                return {
                    "status": ConvergenceStatus.DIVERGING,
                    "steps_remaining": None,
                    "trend": "Forces are INCREASING — geometry may be moving away from minimum",
                }

        return {
            "status": ConvergenceStatus.CONVERGING,
            "steps_remaining": None,
            "trend": "Optimizing — insufficient data to estimate remaining steps",
        }

    def _format_time(self, seconds: Optional[float]) -> str:
        """Format seconds into human-readable string."""
        if seconds is None:
            return "unknown"
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{seconds / 60:.1f}min"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    def generate_summary(self, result: ParseResult) -> str:
        """Generate a human-readable summary of parse results."""
        lines = [
            f"=== {result.code.upper()} Output Analysis ===",
            f"File: {result.file_path}",
            "",
        ]

        # SCF info
        if result.scf_cycles:
            lines.append(f"--- SCF Convergence ---")
            lines.append(f"Cycles completed: {len(result.scf_cycles)}")
            lines.append(f"Status: {result.scf_status.value.upper()}")
            if result.final_energy is not None:
                lines.append(f"Current energy: {result.final_energy:.8f} {result.final_energy_units}")
            if result.avg_time_per_scf:
                lines.append(f"Avg time/cycle: {self._format_time(result.avg_time_per_scf)}")
            if result.scf_time_remaining_seconds is not None:
                lines.append(f"Estimated time remaining: {self._format_time(result.scf_time_remaining_seconds)}")

        # Geo opt info
        if result.geo_steps:
            lines.append(f"\n--- Geometry Optimization ---")
            lines.append(f"Steps completed: {len(result.geo_steps)}")
            if result.geo_converged:
                lines.append("Status: CONVERGED")
            else:
                last = result.geo_steps[-1]
                if last.rms_force is not None:
                    lines.append(f"Current RMS force: {last.rms_force:.6f}")
                if result.geo_steps_remaining is not None:
                    lines.append(f"Estimated steps remaining: {result.geo_steps_remaining}")

        # Errors and Warnings
        if result.errors:
            lines.append(f"\n--- ERRORS ({len(result.errors)}) ---")
            for e in result.errors[:5]:
                lines.append(f"  - {e}")
        if result.warnings:
            lines.append(f"\n--- WARNINGS ({len(result.warnings)}) ---")
            for w in result.warnings[:10]:
                lines.append(f"  - {w}")

        return "\n".join(lines)
