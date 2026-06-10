"""ORCA output (.out) file parser."""

import re
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class ORCAParser(BaseParser):
    """Parser for ORCA output files.

    Extracts:
    - SCF energy convergence
    - Geometry optimization steps
    - Timing information
    - Common errors
    """

    code = "orca"
    scf_convergence_threshold = 1e-8

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Extract SCF cycles
        result.scf_cycles = self._extract_scf_cycles(content)

        # Extract geometry optimization
        result.geo_steps = self._extract_geo_steps(content)

        # Extract errors and warnings
        result.errors = self._extract_errors(content)
        result.warnings = self._extract_warnings(content)

        # Analyze SCF convergence
        if result.scf_cycles:
            analysis = self.analyze_scf_convergence(result.scf_cycles)
            result.scf_status = analysis["status"]
            result.scf_cycles_remaining = analysis["cycles_remaining"]
            result.scf_time_remaining_seconds = analysis["time_remaining"]

            times = [c.time_seconds for c in result.scf_cycles if c.time_seconds]
            if times:
                result.avg_time_per_scf = sum(times) / len(times)

        # Analyze geo convergence
        if result.geo_steps:
            geo_analysis = self.analyze_geo_convergence(result.geo_steps)
            result.geo_converged = result.geo_steps[-1].converged if result.geo_steps else False
            result.geo_steps_remaining = geo_analysis.get("steps_remaining")

        # Final energy
        result.final_energy = self._extract_final_energy(content)
        result.final_energy_units = "Hartree"

        # Elapsed time
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        # Check if completed
        result.success = "****ORCA TERMINATED NORMALLY****" in content

        return result

    def _extract_scf_cycles(self, content: str) -> list:
        """Extract SCF energy convergence from ORCA output.

        ORCA format:
        ITER       Energy         Delta-E        Max-DP    RMS-DP   [F,P]     Damp
               ***  Starting incremental Fock matrix formation  ***
         0   -xxx.xxxxx    0.000000000000  ...
         1   -xxx.xxxxx    -x.xxxxe-03     ...
        ...
        *** SCF ITERATIONS CONVERGED ***
        """
        cycles = []

        # ORCA SCF iteration table: each line looks like:
        #   0   -76.432174802    0.000000000000  ...
        # Sometimes lines start with MA/DA/DIIS label
        scf_pattern = re.compile(
            r"^\s*(?:\d+\s+)?(?:MA|DA|DIIS)?\s*(\d+)\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+)",
            re.MULTILINE,
        )

        # Find the SCF iterations block
        for match in scf_pattern.finditer(content):
            cycle_num = int(match.group(1))
            try:
                energy = float(match.group(2))
            except (ValueError, OverflowError):
                continue

            delta_e = abs(energy - cycles[-1].energy) if cycles else None

            # Try to get delta_e from the match as well
            try:
                de = float(match.group(3))
            except (ValueError, OverflowError):
                de = None

            cycles.append(SCFCycle(cycle=cycle_num, energy=energy, delta_e=delta_e or (
                abs(de) if de is not None else None
            )))

        return cycles

    def _extract_geo_steps(self, content: str) -> list:
        """Extract geometry optimization steps from ORCA output.

        ORCA prints "GEOMETRY OPTIMIZATION CYCLE   N" for each step.
        """
        steps = []

        # Split by geometry optimization cycle markers
        cycle_blocks = re.split(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)", content)

        # cycle_blocks[0] is before first cycle, then [1]=num, [2]=content, [3]=num, [4]=content, ...
        for i in range(1, len(cycle_blocks), 2):
            if i + 1 >= len(cycle_blocks):
                break

            step_num = int(cycle_blocks[i])
            block = cycle_blocks[i + 1]

            # Energy
            energy = None
            en_match = re.search(
                r"(?:FINAL SINGLE POINT ENERGY|Total Energy\s*:|Last energy\s*)\s*([-]?\d+\.\d+)",
                block,
            )
            if en_match:
                energy = float(en_match.group(1))

            # Also check for the energy in the SCF section
            if energy is None:
                scf_energies = re.findall(
                    r"^\s*\d+\s+([-]?\d+\.\d+)",
                    block,
                    re.MULTILINE,
                )
                if scf_energies:
                    energy = float(scf_energies[-1])

            if energy is None:
                continue

            delta_e = abs(energy - steps[-1].energy) if steps else None
            step = GeoStep(step=step_num, energy=energy, delta_e=delta_e)

            # Forces
            # "RMS gradient" or "MAX gradient"
            rms_match = re.search(r"RMS\s+gradient\s*[:=]\s*(\d+\.\d+)", block)
            max_match = re.search(r"MAX\s+gradient\s*[:=]\s*(\d+\.\d+)", block)
            if rms_match:
                step.rms_force = float(rms_match.group(1))
            if max_match:
                step.max_force = float(max_match.group(1))

            # Check convergence
            if "THE OPTIMIZATION HAS CONVERGED" in block:
                step.converged = True

            steps.append(step)

        # Overall convergence check
        if "THE OPTIMIZATION HAS CONVERGED" in content:
            if steps:
                steps[-1].converged = True

        return steps

    def _extract_final_energy(self, content: str) -> float | None:
        """Extract final energy from ORCA output."""
        # "FINAL SINGLE POINT ENERGY"
        m = re.search(r"FINAL SINGLE POINT ENERGY\s+([-]?\d+\.\d+)", content)
        if m:
            return float(m.group(1))

        # Fallback: search for last SCF energy
        scf_energies = re.findall(
            r"^\s*\d+\s+([-]?\d+\.\d+)",
            content,
            re.MULTILINE,
        )
        if scf_energies:
            return float(scf_energies[-1])

        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract total elapsed time from ORCA output."""
        # ORCA prints timing at end: "TOTAL RUN TIME:  0 days  0 hours  1 minutes 12 seconds 345 msec"
        m = re.search(
            r"TOTAL RUN TIME:\s+(\d+)\s*days?\s+(\d+)\s*hours?\s+(\d+)\s*minutes?\s+(\d+)\s*seconds?",
            content,
        )
        if m:
            days, hours, minutes, secs = map(int, m.groups())
            return days * 86400 + hours * 3600 + minutes * 60 + secs

        # Alternative format: "Total time  ....     123.456 sec"
        m = re.search(r"Total\s+time\s+\.{2,}\s+(\d+\.?\d*)\s+sec", content)
        if m:
            return float(m.group(1))

        return None

    def _extract_errors(self, content: str) -> list:
        """Extract error patterns from ORCA output."""
        errors = []

        error_patterns = [
            (r"ORCA finished with an error", "ORCA terminated with error"),
            (r"SCF did not converge", "SCF did not converge — try different SCF settings or initial guess"),
            (r"SCF NOT CONVERGED", "SCF NOT CONVERGED"),
            (r"Too many SCF iterations", "Too many SCF iterations — SCF not converging"),
            (r"Geometry optimization did not converge", "Geometry optimization did not converge"),
            (r"Out of memory", "Out of memory — reduce system size or use RI/RIJCOSX"),
            (r"FILE.*?NOT FOUND", "Input/basis file not found"),
            (r"Unrecognized keyword", "Unrecognized keyword in input — check syntax"),
            (r"Basis set not available for", "Basis set not available for an element"),
            (r"ERROR in atomic coordinates", "Error in atomic coordinates — check geometry input"),
            (r"Charge/multiplicity.*?inconsistent", "Charge/multiplicity inconsistent with number of electrons"),
            (r"Imaginary frequency", "Imaginary frequencies found — not a minimum"),
            (r"Linear dependence detected", "Linear dependence in basis set — try different basis or remove diffuse functions"),
            (r"TDDFT.*?error", "TD-DFT calculation error"),
        ]

        for pattern, msg in error_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(msg)

        return errors

    def _extract_warnings(self, content: str) -> list:
        """Extract warnings from ORCA output."""
        warnings = []

        warning_patterns = [
            (r"WARNING.*?SCF.*?slow", "SCF converging slowly — consider different initial guess or damping"),
            (r"WARNING.*?oscillat", "SCF oscillating — try different mixing or DIIS settings"),
            (r"WARNING.*?linear.*?depend", "Linear dependence detected — results may be unreliable"),
            (r"WARNING.*?small HOMO-LUMO gap", "Small HOMO-LUMO gap — may need multi-reference treatment"),
            (r"WARNING.*?spin contamination", "Spin contamination detected — wavefunction may be unreliable"),
            (r"WARNING.*?negative frequency", "Negative vibrational frequency — not a minimum"),
            (r"WARNING.*?CPHF.*?not converged", "CPHF not converged — property may be inaccurate"),
            (r"WARNING.*?basis set.*?small", "Basis set may be too small for desired accuracy"),
        ]

        for pattern, msg in warning_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(msg)

        return warnings
