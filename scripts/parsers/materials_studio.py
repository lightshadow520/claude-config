"""Materials Studio / CASTEP / DMol3 output parser."""

import re
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class MaterialsStudioParser(BaseParser):
    """Parser for Materials Studio output.

    Supports:
    - CASTEP (.castep output)
    - DMol3 (.outmol output)
    - Forcite (generic)

    These are all Biovia/MS codes that share similar output patterns.
    """

    code = "ms"

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Auto-detect MS sub-code
        sub_code = self._detect_sub_code(content)
        result.raw_headers["sub_code"] = sub_code

        if sub_code == "castep":
            result = self._parse_castep(result, content)
        elif sub_code == "dmol3":
            result = self._parse_dmol3(result, content)

        result.errors = self._extract_errors(content)
        result.warnings = self._extract_warnings(content)
        result.elapsed_time_seconds = self._extract_elapsed_time(content)
        result.success = self._check_success(content, sub_code)

        return result

    def _detect_sub_code(self, content: str) -> str:
        if "CASTEP" in content or "castep" in content.lower():
            return "castep"
        if "DMol3" in content or "Dmol3" in content:
            return "dmol3"
        if "Forcite" in content:
            return "forcite"
        return "unknown"

    def _parse_castep(self, result: ParseResult, content: str) -> ParseResult:
        """Parse CASTEP output.

        CASTEP SCF format:
        ========================
        SCF loop      Energy            Fermi energy      dE
        ========================
        Initial       -xxx.xxxxx        -0.xxxx
           1          -xxx.xxxxx        -0.xxxx        1.23456E-04
           2          -xxx.xxxxx        -0.xxxx        2.34567E-06
        ...
        Final energy = -xxx.xxxxx eV
        """
        cycles = []

        # CASTEP SCF energy lines
        scf_pattern = re.compile(
            r"^\s*(\d+)\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+E[+\-]\d+)",
            re.MULTILINE,
        )

        for m in scf_pattern.finditer(content):
            cycle = int(m.group(1))
            energy = float(m.group(2))
            try:
                de = abs(float(m.group(4)))
            except (ValueError, OverflowError):
                de = None

            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=cycle, energy=energy, delta_e=delta_e))

        result.scf_cycles = cycles

        if cycles:
            analysis = self.analyze_scf_convergence(cycles)
            result.scf_status = analysis["status"]
            result.scf_cycles_remaining = analysis["cycles_remaining"]
            result.scf_time_remaining_seconds = analysis["time_remaining"]

        # Geometry optimization for CASTEP
        geo_steps = self._extract_castep_geo(content)
        result.geo_steps = geo_steps

        if geo_steps:
            geo_analysis = self.analyze_geo_convergence(geo_steps)
            result.geo_converged = geo_steps[-1].converged if geo_steps else False
            result.geo_steps_remaining = geo_analysis.get("steps_remaining")

        # Final energy
        en_match = re.search(r"Final energy\s*=\s*([-]?\d+\.\d+)\s*eV", content)
        if en_match:
            result.final_energy = float(en_match.group(1))
            result.final_energy_units = "eV"

        # Also try BFGS final energy
        if result.final_energy is None:
            en_match = re.search(r"BFGS: Final Enthalpy\s*=\s*([-]?\d+\.\d+)\s*eV", content)
            if en_match:
                result.final_energy = float(en_match.group(1))
                result.final_energy_units = "eV"

        # Total time
        time_match = re.search(r"Total time\s+=\s+(\d+\.?\d*)\s*s", content)
        if time_match:
            result.elapsed_time_seconds = float(time_match.group(1))

        return result

    def _extract_castep_geo(self, content: str) -> list:
        """Extract CASTEP geometry optimization steps.

        CASTEP BFGS output:
        ====================
        BFGS: starting iteration    1 ...
        ====================
        ...
        Final Enthalpy = -xxx.xxxxx eV
        """
        steps = []

        bfgs_blocks = re.split(r"BFGS: starting iteration\s+(\d+)", content)
        for i in range(1, len(bfgs_blocks), 2):
            if i + 1 >= len(bfgs_blocks):
                break

            step_num = int(bfgs_blocks[i])
            block = bfgs_blocks[i + 1]

            energy = None
            en_match = re.search(r"Final Enthalpy\s*=\s*([-]?\d+\.\d+)\s*eV", block)
            if en_match:
                energy = float(en_match.group(1))
            if energy is None:
                en_match = re.search(r"Final energy\s*=\s*([-]?\d+\.\d+)\s*eV", block)
                if en_match:
                    energy = float(en_match.group(1))

            if energy is None:
                continue

            delta_e = abs(energy - steps[-1].energy) if steps else None
            step = GeoStep(step=step_num, energy=energy, delta_e=delta_e)

            # Force extraction
            max_force = re.search(r"max\s+force\s*=\s*(\d+\.?\d*E[+\-]?\d+)", block, re.IGNORECASE)
            rms_force = re.search(r"rms\s+force\s*=\s*(\d+\.?\d*E[+\-]?\d+)", block, re.IGNORECASE)
            if max_force:
                step.max_force = float(max_force.group(1))
            if rms_force:
                step.rms_force = float(rms_force.group(1))

            steps.append(step)

        # Convergence check
        if "BFGS: Geometry optimization completed successfully" in content:
            if steps:
                steps[-1].converged = True

        return steps

    def _parse_dmol3(self, result: ParseResult, content: str) -> ParseResult:
        """Parse DMol3 output.

        DMol3 SCF format:
        Energy of the      1-th Cycle:    -xxx.xxxxx Ha
        Energy of the      2-th Cycle:    -xxx.xxxxx Ha
        ...
        """
        cycles = []

        scf_pattern = re.compile(
            r"Energy of the\s+(\d+)-th Cycle:\s+([-]?\d+\.\d+)\s+Ha",
        )

        for m in scf_pattern.finditer(content):
            cycle = int(m.group(1))
            energy = float(m.group(2))
            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=cycle, energy=energy, delta_e=delta_e))

        result.scf_cycles = cycles

        if cycles:
            analysis = self.analyze_scf_convergence(cycles)
            result.scf_status = analysis["status"]

        # Final energy
        en_match = re.search(r"Total Energy\s*=\s*([-]?\d+\.\d+)\s*Ha", content)
        if en_match:
            result.final_energy = float(en_match.group(1))
            result.final_energy_units = "Hartree"

        # Geo optimization
        geo_steps = []
        geo_blocks = re.split(r"Geometry optimization cycle\s*=\s*(\d+)", content)
        for i in range(1, len(geo_blocks), 2):
            if i + 1 >= len(geo_blocks):
                break
            step_num = int(geo_blocks[i])
            block = geo_blocks[i + 1]

            en_match = re.search(r"Total Energy\s*=\s*([-]?\d+\.\d+)\s*Ha", block)
            if en_match:
                energy = float(en_match.group(1))
                delta_e = abs(energy - geo_steps[-1].energy) if geo_steps else None
                step = GeoStep(step=step_num, energy=energy, delta_e=delta_e)

                rms_match = re.search(r"\|dE/dxyz\|\s*=\s*(\d+\.?\d*E[+\-]?\d+)", block)
                max_match = re.search(r"Max\|dE/dxyz\|\s*=\s*(\d+\.?\d*E[+\-]?\d+)", block)
                if rms_match:
                    step.rms_force = float(rms_match.group(1))
                if max_match:
                    step.max_force = float(max_match.group(1))

                geo_steps.append(step)

        result.geo_steps = geo_steps
        if geo_steps:
            result.geo_converged = geo_steps[-1].converged if geo_steps else False

        return result

    def _extract_elapsed_time(self, content: str) -> float | None:
        # CASTEP
        m = re.search(r"Total time\s+=\s+(\d+\.?\d*)\s*s", content)
        if m:
            return float(m.group(1))
        # DMol3
        m = re.search(r"Total cpu time\s*=\s*(\d+\.?\d*)\s*s", content, re.IGNORECASE)
        if m:
            return float(m.group(1))
        # Wall time
        m = re.search(r"Total wall time\s*=\s*(\d+\.?\d*)\s*s", content, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    def _check_success(self, content: str, sub_code: str) -> bool:
        if sub_code == "castep":
            return "Job done" in content or "Total time" in content
        if sub_code == "dmol3":
            return "successful completion" in content.lower()
        return False

    def _extract_errors(self, content: str) -> list:
        errors = []

        patterns = [
            (r"ERROR:\s*(.*?)\n", None),
            (r"SCF convergence.*?failed", "SCF convergence failed — try different mixing or smearing"),
            (r"CATASTROPHIC ERROR", "Catastrophic error — calculation aborted"),
            (r"Not enough memory", "Out of memory"),
            (r"Pseudopotential.*?not found", "Pseudopotential file not found"),
            (r"Cell too small", "Unit cell too small for given cutoff"),
            (r"k-point.*?error", "K-point setup error"),
            (r"Geometry optimization.*?failed", "Geometry optimization failed"),
            (r"Maximum number of SCF cycles", "Max SCF cycles exceeded — not converging"),
            (r"Charge.*?not an integer", "Non-integer total charge — check atom types/charges"),
            (r"Basis set.*?error", "Basis set error"),
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
            (r"WARNING:\s*(.*?)\n", None),
            (r"SCF convergence.*?slow", "SCF converging slowly"),
            (r"Electronic minimization.*?not.*?accurate", "Electronic minimization may not be fully accurate"),
            (r"Stress.*?large", "Large residual stress — cell may need relaxation"),
            (r"Occupation.*?smearing", "Smearing active — check for metallic behavior"),
            (r"Density mixing.*?adjusted", "Density mixing auto-adjusted"),
        ]

        for pattern, msg in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if msg is None and match.groups() and "WARNING" in match.group(0).upper():
                    warnings.append(match.group(1).strip())
                elif msg:
                    warnings.append(msg)

        return warnings
