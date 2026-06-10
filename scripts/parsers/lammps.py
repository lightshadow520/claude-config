"""LAMMPS log file parser."""

import re
from .base import BaseParser, ParseResult, ConvergenceStatus


class LAMMPSParser(BaseParser):
    """Parser for LAMMPS log files.

    LAMMPS is an MD code — the concept is different from SCF convergence.
    Key metrics:
    - Thermo output: step, temp, press, pe, ke, total energy
    - Energy conservation (NVE): fluctuation of total energy
    - Equilibration detection: temperature/pressure stabilization
    - Minimization: force/energy convergence
    """

    code = "lammps"

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Extract thermo data
        thermo = self._extract_thermo(content)
        result.raw_headers["thermo_columns"] = thermo.get("columns", [])
        result.raw_headers["thermo_count"] = len(thermo.get("data", []))

        # Extract errors and warnings
        result.errors = self._extract_errors(content)
        result.warnings = self._extract_warnings(content)

        # For minimization: extract energy and force convergence
        if thermo.get("data"):
            result = self._analyze_minimization(result, thermo)
            result = self._analyze_md_equilibration(result, thermo)
            result = self._analyze_energy_drift(result, thermo)

        # Timing
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        # Success
        result.success = "Total wall time:" in content

        return result

    def _extract_thermo(self, content: str) -> dict:
        """Extract thermo output from LAMMPS log.

        LAMMPS thermo format:
        Step Temp Press TotEng ...
            0    300  1.0    -1234.5 ...
          100    298  1.0    -1234.8 ...
        """
        # Find thermo blocks — they start with column headers
        thermo_blocks = re.split(r"Step\s+(?:Temp|Press)", content)

        columns = ["Step"]
        data = []

        # Find the header line
        header_match = re.search(
            r"^(Step\s+.*?)\n\s*\n",
            content,
            re.MULTILINE,
        )
        if header_match:
            header_line = header_match.group(1)
            columns = header_line.split()
        else:
            # Try finding column names in a "Per MPI rank" style output
            header_match = re.search(r"Step\s+([A-Za-z_]+\s+)+", content)
            if header_match:
                columns = header_match.group(0).split()

        # Find the data sections (after the header, before "Loop time")
        # Try matching numeric thermo lines
        if columns:
            # Build a pattern for the numeric columns
            col_count = len(columns)
            num_pattern = r"^\s*(\d+)\s+(" + r"\s+".join([r"([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)"] * (col_count - 1)) + r")"
            num_re = re.compile(num_pattern, re.MULTILINE)

            for m in num_re.finditer(content):
                row = [int(m.group(1))]
                for j in range(2, col_count + 1):
                    try:
                        row.append(float(m.group(j)))
                    except (ValueError, IndexError):
                        row.append(0.0)
                data.append(row)

        # Also try simpler pattern: just extract all lines that look like thermo data
        if not data:
            # Find "Step" marker and extract subsequent numeric lines
            thermo_lines = re.findall(
                r"^\s*(\d+)\s+([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)\s+([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)",
                content,
                re.MULTILINE,
            )
            for step, val1, val2 in thermo_lines:
                data.append([int(step), float(val1), float(val2)])

        return {"columns": columns, "data": data}

    def _analyze_minimization(self, result: ParseResult, thermo: dict) -> ParseResult:
        """Analyze energy minimization convergence."""
        data = thermo.get("data", [])
        columns = thermo.get("columns", [])

        if not data or len(data) < 2:
            return result

        # Check if this is a minimization run
        # LAMMPS minimization has fewer steps and energy decreases
        energies = []
        energy_col = self._find_column(columns, "TotEng", "PotEng", "Energy", "pe")

        for row in data:
            if energy_col is not None and energy_col < len(row):
                energies.append(float(row[energy_col]))

        if energies and len(energies) >= 3:
            first = energies[:3]
            last = energies[-3:]
            avg_first = sum(first) / 3
            avg_last = sum(last) / 3

            if avg_first > avg_last:  # Energy decreasing = minimization
                de = abs(avg_last - avg_first)
                if de < 1e-10:
                    result.scf_status = ConvergenceStatus.CONVERGED
                else:
                    result.scf_status = ConvergenceStatus.CONVERGING

        return result

    def _analyze_md_equilibration(self, result: ParseResult, thermo: dict) -> ParseResult:
        """Check if MD is equilibrated by analyzing temperature/pressure stability."""
        data = thermo.get("data", [])
        columns = thermo.get("columns", [])

        if len(data) < 100:
            result.raw_headers["equilibration"] = "insufficient_data"
            return result

        temp_col = self._find_column(columns, "Temp", "temperature", "T")
        if temp_col is None:
            return result

        temps = [float(row[temp_col]) for row in data[-100:] if temp_col < len(row)]
        if temps:
            avg = sum(temps) / len(temps)
            variance = sum((t - avg) ** 2 for t in temps) / len(temps)
            std = variance ** 0.5
            result.raw_headers["temp_avg"] = avg
            result.raw_headers["temp_std"] = std

            if std / max(abs(avg), 1) < 0.01:
                result.raw_headers["equilibration"] = "equilibrated"
            elif std / max(abs(avg), 1) < 0.05:
                result.raw_headers["equilibration"] = "near_equilibrium"
            else:
                result.raw_headers["equilibration"] = "not_equilibrated"

        return result

    def _analyze_energy_drift(self, result: ParseResult, thermo: dict) -> ParseResult:
        """Check for energy drift in NVE or NVT ensemble."""
        data = thermo.get("data", [])
        columns = thermo.get("columns", [])

        if len(data) < 100:
            return result

        energy_col = self._find_column(columns, "TotEng", "etotal", "TotEn", "pe")
        if energy_col is None:
            return result

        energies = [float(row[energy_col]) for row in data if energy_col < len(row)]
        if len(energies) >= 100:
            first_quarter = energies[:len(energies) // 4]
            last_quarter = energies[-len(energies) // 4:]
            drift = abs(sum(last_quarter) / len(last_quarter) - sum(first_quarter) / len(first_quarter))

            result.raw_headers["energy_drift"] = drift
            if drift > 1e-3 * len(data):  # Significant drift
                result.warnings.append(f"Energy drift detected: {drift:.4e} per {len(data)} steps")

        return result

    def _find_column(self, columns: list, *names: str) -> int | None:
        """Find a column index by possible names (case-insensitive)."""
        names_lower = [n.lower() for n in names]
        for i, col in enumerate(columns):
            if col.lower() in names_lower:
                return i
        # Partial match
        for i, col in enumerate(columns):
            for name in names_lower:
                if name.lower() in col.lower():
                    return i
        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract wall time from LAMMPS output."""
        m = re.search(r"Total wall time:\s+(\d+):(\d+):(\d+)", content)
        if m:
            h, m_val, s = map(int, m.groups())
            return h * 3600 + m_val * 60 + s

        m = re.search(r"Loop time of\s+(\d+\.?\d*)\s+on", content)
        if m:
            return float(m.group(1))

        return None

    def _extract_errors(self, content: str) -> list:
        errors = []

        patterns = [
            (r"ERROR on proc \d+", "LAMMPS error — check the specific error message above"),
            (r"ERROR: (.*?)\n", None),  # capture specific error message
            (r"Bond/atom missing", "Missing bond or atom definition"),
            (r"Angle/atom missing", "Missing angle/atom definition"),
            (r"Non-numeric atom coordinate", "Non-numeric coordinate in data file"),
            (r"Out of range atoms", "Atom coordinates out of simulation box"),
            (r"Lost atoms.*?check.*?thermo", "Atoms lost — check timestep or initial geometry"),
            (r"Shake.*?not converged", "SHAKE algorithm not converged"),
            (r"Cannot open.*?file", "Cannot open input or data file"),
            (r"Pair coeff.*?not set", "Pair coefficients not set for all atom types"),
            (r"Too many neighbor list builds", "Too many neighbor builds — atoms may overlap, check geometry"),
            (r"Timestep.*?too large", "Timestep too large — atoms moving too fast"),
            (r"PPPM.*?error", "PPPM (long-range electrostatics) error"),
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
            (r"WARNING: (.*?)\n", None),
            (r"System is not charge neutral", "System not charge neutral — check atom charges"),
            (r"Dangerous builds", "Dangerous neighbor list build count"),
            (r"Communication.*?cutoff.*?may be too large", "Communication cutoff may be too large for efficiency"),
            (r"Temperature.*?out of range", "Temperature outside expected range"),
            (r"Pressure.*?out of range", "Pressure outside expected range"),
        ]

        for pattern, msg in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if msg is None and match.groups():
                    warnings.append(match.group(1).strip())
                elif msg:
                    warnings.append(msg)

        return warnings
