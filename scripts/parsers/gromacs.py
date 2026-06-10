"""GROMACS output parser (.log, .edr energy data)."""

import re
import os
from .base import BaseParser, ParseResult, ConvergenceStatus


class GROMACSParser(BaseParser):
    """Parser for GROMACS log files and energy output.

    GROMACS is MD-focused. Key metrics:
    - Energy minimization: Fmax convergence
    - MD equilibration: T/P stability
    - Production MD: energy conservation, drift
    - Performance: ns/day, hours remaining

    GROMACS log has distinctive sections:
    - "Steepest Descents" or "Conjugate Gradients" for EM
    - "Step" lines for MD progress
    - "Performance" section at the end
    """

    code = "gromacs"

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Detect calculation type
        calc_type = self._detect_type(content)
        result.raw_headers["calc_type"] = calc_type

        # Extract energy minimization convergence
        result = self._extract_em_convergence(result, content)

        # Extract MD progress
        result = self._extract_md_progress(result, content)

        # Performance metrics
        result = self._extract_performance(result, content)

        # Errors and warnings
        result.errors = self._extract_errors(content)
        result.warnings = self._extract_warnings(content)

        # Timing
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        result.success = "Finished mdrun" in content or "writing final coordinates" in content.lower()

        return result

    def _detect_type(self, content: str) -> str:
        if "Steepest Descents" in content or "Conjugate Gradients" in content:
            return "Energy Minimization"
        if "NVT" in content and "NPT" not in content:
            return "NVT Equilibration"
        if "NPT" in content:
            return "NPT Equilibration"
        if "MD" in content and "nsteps" in content.lower():
            return "MD Production"
        return "Unknown"

    def _extract_em_convergence(self, result: ParseResult, content: str) -> ParseResult:
        """Extract energy minimization convergence.

        GROMACS EM format:
        Step    0: Fmax= 1.234e+03, atom= 42
        Step    1: Fmax= 8.765e+02, atom= 42
        ...
        Energy minimization has converged to Fmax < 1000
        """
        em_steps = re.findall(
            r"Step\s+(\d+).*?Fmax=\s*(\d+\.?\d*(?:[eE][+\-]?\d+)?)",
            content,
        )
        if not em_steps:
            return result

        from .base import SCFCycle
        cycles = []
        for i, (step_str, fmax_str) in enumerate(em_steps):
            fmax = float(fmax_str)
            cycles.append(SCFCycle(cycle=int(step_str), energy=fmax, delta_e=(
                abs(fmax - cycles[-1].energy) if cycles else None
            )))

        result.scf_cycles = cycles
        if cycles:
            if "converged to Fmax" in content:
                result.scf_status = ConvergenceStatus.CONVERGED
            else:
                # Check force trend
                if len(cycles) >= 3:
                    recent = [c.energy for c in cycles[-3:]]
                    if recent[-1] < recent[-2] < recent[-3]:
                        result.scf_status = ConvergenceStatus.CONVERGING
                    else:
                        result.scf_status = ConvergenceStatus.STUCK

        return result

    def _extract_md_progress(self, result: ParseResult, content: str) -> ParseResult:
        """Extract MD simulation progress.

        GROMACS prints "Step" progress during MD:
        Step 1000000, time 2000 (ps)  LINCS WARNING
        ...Performance: 123.456 ns/day
        """
        # Find total steps
        nsteps_match = re.search(r"nsteps\s*=\s*(\d+)", content)
        total_steps = int(nsteps_match.group(1)) if nsteps_match else None
        result.raw_headers["total_steps"] = total_steps

        # Find current step (last step reported)
        step_matches = re.findall(r"Step\s+(\d+)", content)
        if step_matches:
            current_step = int(step_matches[-1])
            result.raw_headers["current_step"] = current_step

            if total_steps and total_steps > 0:
                fraction = current_step / total_steps
                result.raw_headers["progress"] = f"{fraction:.1%}"

                # Estimate time remaining from performance
                ns_per_day = self._extract_ns_per_day(content)
                if ns_per_day:
                    result.raw_headers["ns_per_day"] = ns_per_day

        return result

    def _extract_performance(self, result: ParseResult, content: str) -> ParseResult:
        """Extract performance metrics (ns/day, hours remaining)."""
        ns_per_day = self._extract_ns_per_day(content)
        if ns_per_day:
            result.raw_headers["ns_per_day"] = ns_per_day

        hours_remaining = re.search(r"Estimated time to finish.*?:\s+(\d+):(\d+)", content)
        if hours_remaining:
            h, m = map(int, hours_remaining.groups())
            result.raw_headers["hours_remaining"] = h + m / 60.0

        # "Performance:" line
        perf_match = re.search(r"Performance:\s+(\d+\.?\d*)\s+ns/day", content)
        if perf_match:
            ns_day = float(perf_match.group(1))
            result.raw_headers["ns_per_day"] = ns_day

            # Calculate remaining time if we know current step
            current_step = result.raw_headers.get("current_step")
            total_steps = result.raw_headers.get("total_steps")
            # Rough: 1000 steps * timestep = 1ps (typical)
            dt_match = re.search(r"dt\s*=\s*(\d+\.?\d*)", content)
            if dt_match and current_step and total_steps:
                dt_ps = float(dt_match.group(1)) / 1000.0  # fs -> ps
                remaining_steps = total_steps - current_step
                remaining_ps = remaining_steps * dt_ps
                if ns_day > 0:
                    hours_per_ns = 24
                    remaining_hours = (remaining_ps / 1000) / ns_day * 24
                    result.raw_headers["estimated_remaining_hours"] = remaining_hours

        return result

    def _extract_ns_per_day(self, content: str) -> float | None:
        """Extract ns/day from performance output."""
        m = re.search(r"Performance:\s+(\d+\.?\d*)\s+ns/day", content)
        if m:
            return float(m.group(1))
        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract wall time from GROMACS log."""
        m = re.search(r"real\s+(\d+)h(\d+)", content)
        if m:
            return float(m.group(1)) * 3600 + float(m.group(2)) * 60
        m = re.search(r"Total Time:\s+(\d+\.?\d*)\s+\(sec\)", content)
        if m:
            return float(m.group(1))
        return None

    def _extract_errors(self, content: str) -> list:
        errors = []

        patterns = [
            (r"Fatal error:\s*(.*?)\n", None),
            (r"Atom (\d+) in multiple T-Coupling groups", "Atom in multiple T-coupling groups"),
            (r"Atom (\d+) is missing", "Atom missing from topology"),
            (r"XTC file corruption", "XTC trajectory file corrupted"),
            (r"No such moleculetype", "Undefined molecule type in topology"),
            (r"Too many LINCS warnings", "Too many LINCS constraint failures — reduce timestep"),
            (r"[Cc]ould not [Ff]ind", "File not found"),
            (r"Segmentation fault", "Segmentation fault — possible memory or topology issue"),
            (r"Bond length.*?too large", "Unrealistic bond length — check topology/initial geometry"),
            (r"1-4 interaction.*?distance larger", "Atoms too close in starting geometry"),
            (r"system is exploding", "System exploding — atoms moving too fast through each other"),
            (r"infinite pressure", "Infinite pressure — atoms overlapping or vacuum space too large"),
        ]

        for pattern, msg in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if msg is None and match.groups():
                    errors.append(match.group(1).strip())
                elif msg:
                    errors.append(msg)

        return errors

    def _extract_warnings(self, content: str) -> list:
        warnings = []

        patterns = [
            (r"WARNING:?\s*(.*?)\n", None),
            (r"LINCS WARNING.*?relative constraint deviation", "LINCS constraint too large — reduce timestep"),
            (r"Water molecule.*?cannot be settled", "SETTLE constraint failed for water"),
            (r"Pressure scaling.*?more than", "Pressure scaling too large"),
            (r"Long-range correction.*?may be inaccurate", "Long-range LJ correction issue with small box"),
            (r"Note.*?Verlet.*?buffer.*?automatically", "Verlet buffer auto-adjusted — may affect performance"),
        ]

        for pattern, msg in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if msg is None and match.groups() and "WARNING" in match.group(0).upper():
                    warnings.append(match.group(1).strip())
                elif msg:
                    warnings.append(msg)

        return warnings
