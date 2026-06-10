"""Gaussian .log file parser."""

import re
import os
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class GaussianParser(BaseParser):
    """Parser for Gaussian output (.log) files.

    Extracts:
    - SCF energy convergence (DFT, HF, MP2, CC, etc.)
    - Geometry optimization steps
    - Timing per SCF and per geo step
    - Common errors (l1/l2 convergence failure, 502, etc.)
    """

    code = "gaussian"
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

        # Extract geometry optimization steps
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

            # Calculate timing
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

        # Total elapsed time
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        # Check if calculation completed normally
        result.success = "Normal termination" in content

        return result

    def _extract_scf_cycles(self, content: str) -> list:
        """Extract SCF energy cycles from Gaussian output.

        Handles: SCF Done, E= ... after N cycles
        Also extracts per-iteration energies from the SCF iteration table.
        """
        cycles = []

        # Pattern for individual SCF iterations in the detailed table
        # E= -123.456... or Ene= -123.456...
        iter_pattern = re.compile(
            r"(?:^\s*\d+\s+)?[-]?\d+\.\d{8,}\s+[-]?\d+\.\d{8,}\s+([-]?\d+\.\d{6,10})",
            re.MULTILINE,
        )

        # More robust: find the "SCF Done" lines which give exact energies per cycle
        scf_done_pattern = re.compile(
            r"SCF Done:\s*E\(\w+\)\s*=\s*([-]?\d+\.\d+)",
        )
        matches = scf_done_pattern.findall(content)

        for i, energy_str in enumerate(matches, 1):
            energy = float(energy_str)
            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=i, energy=energy, delta_e=delta_e))

        # If no "SCF Done" found, try the iteration table
        if not cycles:
            # Find SCF iteration blocks
            iter_blocks = re.finditer(
                r"(?:Cycle|Iter)\s+\d+\s+.*?([-]?\d+\.\d{8,}).*?([-]?\d+\.\d+)",
                content,
            )
            for i, m in enumerate(iter_blocks, 1):
                energy = float(m.group(1))
                delta_e = abs(energy - cycles[-1].energy) if cycles else None
                cycles.append(SCFCycle(cycle=i, energy=energy, delta_e=delta_e))

        # Try to extract timing per SCF from Gaussian's timing output
        # "Job cpu time:  0 days  0 hours  1 minutes 12.3 seconds."
        if cycles:
            time_pattern = re.search(
                r"Job cpu time:\s+\d+ days\s+\d+ hours\s+\d+ minutes\s+(\d+\.?\d*) seconds",
                content,
            )
            if time_pattern:
                # total cpu time across all SCF cycles
                # This is rough; Gaussian doesn't give per-cycle timing easily
                pass

        return cycles

    def _extract_geo_steps(self, content: str) -> list:
        """Extract geometry optimization steps."""
        steps = []

        # Gaussian prints "Step number   N" for each optimization step
        step_blocks = re.split(r"(?:Step number\s+\d+|GradGradGradGrad)", content)

        # Better: find all energy values for optimization steps
        # "SCF Done:" after optimization steps
        opt_pattern = re.compile(
            r"Step number\s+(\d+).*?"
            r"SCF Done:.*?=\s*([-]?\d+\.\d+)",
            re.DOTALL,
        )
        for m in opt_pattern.finditer(content):
            step_num = int(m.group(1))
            energy = float(m.group(2))
            delta_e = abs(energy - steps[-1].energy) if steps else None
            steps.append(GeoStep(step=step_num, energy=energy, delta_e=delta_e))

        # Check for convergence in each step block
        # "Maximum Force ... RMS Force ... Maximum Displacement ... RMS Displacement"
        conv_blocks = re.split(r"Step number\s+\d+", content)
        for i, block in enumerate(conv_blocks[1:], 1):
            if i <= len(steps):
                # Check convergence criteria
                if "Converged?" in block:
                    criteria = re.findall(r"(YES|NO)\s*\n", block)
                    if all(c.strip() == "YES" for c in criteria):
                        steps[i - 1].converged = True

                # Extract forces
                rms_force = self._extract_force_value(block, "RMS\s+Force")
                max_force = self._extract_force_value(block, "Maximum\s+Force")
                if rms_force is not None:
                    steps[i - 1].rms_force = rms_force
                if max_force is not None:
                    steps[i - 1].max_force = max_force

        return steps

    def _extract_force_value(self, text: str, label: str) -> float | None:
        """Extract force/displacement convergence value."""
        m = re.search(rf"{label}\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(YES|NO)", text)
        if m:
            return float(m.group(1))
        return None

    def _extract_final_energy(self, content: str) -> float | None:
        """Extract the final SCF energy."""
        # "SCF Done:" is the per-cycle energy, last one is final
        energies = re.findall(r"SCF Done:\s*E\(\w+\)\s*=\s*([-]?\d+\.\d+)", content)
        if energies:
            return float(energies[-1])
        # Fallback: HF/DFT energy summary
        m = re.search(r"Sum of electronic and zero-point Energies=\s*([-]?\d+\.\d+)", content)
        if m:
            return float(m.group(1))
        m = re.search(r"Sum of electronic and thermal Free Energies=\s*([-]?\d+\.\d+)", content)
        if m:
            return float(m.group(1))
        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract total elapsed time in seconds."""
        m = re.search(
            r"Job cpu time:\s+(\d+) days\s+(\d+) hours\s+(\d+) minutes\s+(\d+\.?\d*) seconds",
            content,
        )
        if m:
            days, hours, minutes, secs = map(float, m.groups())
            return days * 86400 + hours * 3600 + minutes * 60 + secs
        return None

    def _extract_errors(self, content: str) -> list:
        """Extract error messages."""
        errors = []

        error_patterns = [
            (r"l1\s+exceeds.*?([\d.]+)", "l1 convergence failure"),
            (r"l2\s+exceeds.*?([\d.]+)", "l2 convergence failure"),
            (r"Convergence failure.*?run terminated", "SCF convergence failure — calculation terminated"),
            (r"Error termination.*?l\d+\.exe", "Gaussian error termination (l1/l2 crash)"),
            (r"Out-of-memory", "Out of memory — reduce basis set or system size"),
            (r"File lengths mismatch", "File corruption — restart from clean directory"),
            (r"atomic number.*?is out of range", "Basis set not available for an atom — check element assignment"),
            (r"Exceeded max SCF cycles", "Max SCF cycles exceeded — not converged within limit"),
            (r"Error termination via Lnk1e", "Link 1 error termination — check input for syntax errors"),
            (r"angle.*is near \d+\.\d+ degrees", "Near-linear angle detected — check geometry"),
            (r"Bend failed for atom", "z-matrix optimization failed — check z-matrix variables"),
            (r"distance between atoms.*is too close", "Atoms too close — possible atomic overlap"),
            (r"MaxMem.*?cannot allocate", "Memory allocation failure — reduce %Mem or use smaller basis"),
            (r"Unknown center", "Unknown element in basis set specification"),
        ]

        for pattern, msg in error_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(msg)

        # Check for termination type
        if "Normal termination" not in content:
            term = re.search(r"Error termination.*?(l\d+\.exe|Lnk1e)", content)
            if term:
                errors.append(f"Abnormal termination at {term.group(1)}")

        return errors

    def _extract_warnings(self, content: str) -> list:
        """Extract warning messages."""
        warnings = []

        warning_patterns = [
            (r"Warning.*?linear dependencies", "Linear dependency in basis set — possible near-linear dependence"),
            (r"Warning.*?Max.*?force.*?converged", "Force convergence warning — may not be tight enough"),
            (r"SCF.*?not.*?converged.*?taking.*?dem", "SCF not converged — using density matrix from last cycle"),
            (r"imaginary frequencies", "Imaginary frequencies detected — geometry may not be a true minimum"),
            (r"negative eigenvalue", "Negative eigenvalue in Hessian — not a minimum"),
            (r"Warning.*?symmetry", "Symmetry warning — point group may have changed"),
            (r"Warning.*?near.*?linear", "Near-linear angle — potential optimization issue"),
        ]

        for pattern, msg in warning_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(msg)

        return warnings

    # Gaussian-specific helper utils

    @staticmethod
    def detect_route_section(content: str) -> str | None:
        """Extract the route section (method/basis)."""
        m = re.search(r"#p?\s+(.+?)\n\s*\n", content)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def detect_job_type(content: str) -> str:
        """Detect calculation type: SP, Opt, Freq, TS, etc."""
        # Check route section
        route = GaussianParser.detect_route_section(content) or ""

        if "opt" in route.lower():
            if "freq" in route.lower():
                return "Opt+Freq"
            return "Geometry Optimization"
        if "freq" in route.lower():
            return "Frequency"
        if "irc" in route.lower():
            return "IRC"
        if "ts" in route.lower() or "opt=qst" in route.lower():
            return "Transition State Search"
        if "scan" in route.lower():
            return "Potential Energy Scan"
        if "td" in route.lower() or "cis" in route.lower():
            return "Excited State"
        if "nmr" in route.lower():
            return "NMR"
        return "Single Point Energy"
