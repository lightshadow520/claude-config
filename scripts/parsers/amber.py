"""AMBER output (.out) file parser."""

import re
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class AMBERParser(BaseParser):
    """Parser for AMBER/sander/pmemd output files.

    AMBER is MD-focused. Key sections:
    - Energy minimization (minimization steps with energy)
    - MD (thermodynamic output every ntpr steps)
    - NMR restraints if present
    """

    code = "amber"

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Detect calculation type
        result.raw_headers["calc_type"] = self._detect_type(content)

        # Extract minimization energy
        result = self._extract_minimization(result, content)

        # Extract MD thermo
        result = self._extract_md_thermo(result, content)

        # Errors and warnings
        result.errors = self._extract_errors(content)
        result.warnings = self._extract_warnings(content)

        result.elapsed_time_seconds = self._extract_elapsed_time(content)
        result.success = "|  Total wall time:" in content

        return result

    def _detect_type(self, content: str) -> str:
        if re.search(r"imin\s*=\s*1", content) or "STEEPEST DESCENT" in content:
            return "Energy Minimization"
        if re.search(r"ntb\s*=\s*1", content):
            return "NVE MD"
        if re.search(r"ntb\s*=\s*2", content) and re.search(r"ntp\s*=\s*0", content):
            return "NVT MD"
        if re.search(r"ntp\s*=\s*1", content):
            return "NPT MD"
        return "MD"

    def _extract_minimization(self, result: ParseResult, content: str) -> ParseResult:
        """Extract energy minimization steps from AMBER output.

        Format:
           NSTEP       ENERGY          RMS            GMAX         NAME
              0       -1.2345E+03      2.3456E+02     1.2345E+03     CA
            ...
        """
        cycles = []

        # Find minimization energy table
        min_pattern = re.compile(
            r"^\s*(\d+)\s+([-]?\d+\.\d+E[+\-]\d+)\s+(\d+\.\d+E[+\-]\d+)\s+(\d+\.\d+E[+\-]\d+)",
            re.MULTILINE,
        )

        for m in min_pattern.finditer(content):
            step = int(m.group(1))
            energy = float(m.group(2))
            rms = float(m.group(3))
            gmax = float(m.group(4))

            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=step, energy=energy, delta_e=delta_e,
                                    rms_density=rms, max_density=gmax))

        if cycles:
            result.scf_cycles = cycles

            if len(cycles) >= 2:
                last_de = abs(cycles[-1].energy - cycles[-2].energy)
                if last_de < 1e-5:
                    result.scf_status = ConvergenceStatus.CONVERGED
                else:
                    result.scf_status = ConvergenceStatus.CONVERGING

        return result

    def _extract_md_thermo(self, result: ParseResult, content: str) -> ParseResult:
        """Extract MD thermodynamic output.

        AMBER MD output:
        NSTEP =     1000   TIME(PS) =      10.000  TEMP(K) =   298.15  PRESS =     1.0
        Etot   =    -12345.6789  EKtot   =      1234.5678  EPtot   =    -13580.2467
        BOND   =       123.4567  ANGLE   =       234.5678  DIHED      =      345.6789
        ...
        """
        # Extract density (important for equilibration check)
        density_matches = re.findall(r"Density\s*=\s*(\d+\.?\d*)", content)
        if density_matches:
            densities = [float(d) for d in density_matches]
            result.raw_headers["density_values"] = len(densities)
            if len(densities) >= 3:
                result.raw_headers["density_avg"] = sum(densities[-10:]) / min(10, len(densities))
                result.raw_headers["density_std"] = (
                    sum((d - result.raw_headers["density_avg"]) ** 2
                         for d in densities[-10:]) / min(10, len(densities))
                ) ** 0.5

        # Extract temperature
        temp_matches = re.findall(r"TEMP\(K\)\s*=\s*(\d+\.?\d*)", content)
        if temp_matches:
            temps = [float(t) for t in temp_matches]
            result.raw_headers["temp_avg"] = sum(temps[-10:]) / min(10, len(temps))
            if len(temps) >= 10:
                result.raw_headers["temp_std"] = (
                    sum((t - result.raw_headers["temp_avg"]) ** 2
                         for t in temps[-10:]) / 10
                ) ** 0.5

        # Extract total energy
        etot_matches = re.findall(r"Etot\s*=\s*([-]?\d+\.?\d*)", content)
        if etot_matches:
            etots = [float(e) for e in etot_matches]
            result.raw_headers["energy_drift"] = abs(etots[-1] - etots[0]) if len(etots) >= 2 else 0

        # Progress tracking
        step_matches = re.findall(r"NSTEP\s*=\s*(\d+)", content)
        if step_matches:
            current_step = int(step_matches[-1])
            result.raw_headers["current_step"] = current_step

            # Find nstlim (total steps) from input echo
            nstlim = re.search(r"nstlim\s*=\s*(\d+)", content)
            if nstlim:
                total = int(nstlim.group(1))
                result.raw_headers["total_steps"] = total
                result.raw_headers["progress"] = f"{current_step / total:.1%}"

        return result

    def _extract_elapsed_time(self, content: str) -> float | None:
        m = re.search(r"\|  Total wall time:\s+(\d+):(\d+):(\d+)", content)
        if m:
            h, min_val, s = map(int, m.groups())
            return h * 3600 + min_val * 60 + s
        return None

    def _extract_errors(self, content: str) -> list:
        errors = []

        patterns = [
            (r"ERROR:\s*(.*?)\n", None),
            (r"vlimit exceeded for step", "Velocity limit exceeded — atoms moving too fast, check structure"),
            (r"Coordinate reset.*?cannot be accomplished", "Coordinate reset/restart failed — check restart file"),
            (r"Parameter file not found", "prmtop/inpcrd file not found"),
            (r"Could not find.*?restraint file", "Restraint file not found"),
            (r"Too many vlimit", "Too many velocity limit violations — system unstable"),
            (r"average |v| is NaN", "NaN velocity — system exploded"),
            (r"NAN in energy", "NaN in energy calculation — atoms likely crashed into each other"),
            (r"System is not net neutral", "System not charge neutral — add counterions"),
            (r"Bonded interaction not found", "Missing bonded parameters in force field"),
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
            (r"vlimit.*?exceeded", "Velocity limit exceeded — may indicate system instability"),
            (r"Temperature.*?outside.*?range", "Temperature outside expected range"),
            (r"NMR restraints", "NMR restraints active — energy trends may differ from unrestrained"),
            (r"|  Warmup", "System warming up — data may not be equilibrated yet"),
        ]

        for pattern, msg in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if msg is None and match.groups() and "WARNING" in match.group(0).upper():
                    warnings.append(match.group(1).strip())
                elif msg:
                    warnings.append(msg)

        return warnings
