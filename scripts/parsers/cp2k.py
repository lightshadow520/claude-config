"""CP2K output file parser."""

import re
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class CP2KParser(BaseParser):
    """Parser for CP2K output files.

    CP2K uses a dual GPW/GAPW method and the output format is distinctive:
    - SCF convergence with outer SCF loops
    - OT (Orbital Transformation) or diagonalization methods
    - GEO_OPT with per-step reporting
    """

    code = "cp2k"
    scf_convergence_threshold = 1e-7

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

        # Analyze
        if result.scf_cycles:
            analysis = self.analyze_scf_convergence(result.scf_cycles)
            result.scf_status = analysis["status"]
            result.scf_cycles_remaining = analysis["cycles_remaining"]
            result.scf_time_remaining_seconds = analysis["time_remaining"]

            times = [c.time_seconds for c in result.scf_cycles if c.time_seconds]
            if times:
                result.avg_time_per_scf = sum(times) / len(times)

        if result.geo_steps:
            geo_analysis = self.analyze_geo_convergence(result.geo_steps)
            result.geo_converged = result.geo_steps[-1].converged if result.geo_steps else False
            result.geo_steps_remaining = geo_analysis.get("steps_remaining")

        result.final_energy = self._extract_final_energy(content)
        result.final_energy_units = "Hartree"
        result.elapsed_time_seconds = self._extract_elapsed_time(content)
        result.raw_headers["outer_scf"] = self._get_outer_scf_info(content)
        result.success = "PROGRAM ENDED AT" in content or "PROGRAM STOPPED IN" in content

        return result

    def _extract_scf_cycles(self, content: str) -> list:
        """Extract SCF cycles from CP2K output.

        Actual CP2K OT format (from real output):
             1 OT CG       0.12E+00   44.8     0.00002264     -76.4321748021 -7.64E+01
            62 OT CG       0.85E-01   44.9     0.00000985     -76.4321748022 -1.69E-05
          *** SCF run converged in    62 steps ***

        Plus outer SCF:
          outer SCF iter =    1 RMS gradient =   0.23E-04 energy =      -5438.8122523095
          outer SCF loop converged in   2 iterations or  522 steps

        We extract the last inner SCF block (most recent geo step).
        """
        cycles = []

        # Find all OT CG lines: flexible whitespace between fields
        # Fields: step_num  OT  method  energy_change  time  convergence  total_energy  delta_e
        ot_pattern = re.compile(
            r"^\s*(\d+)\s+OT\s+\w+\s+(\d+\.\d+E[+\-]\d+)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+E[+\-]\d+)",
            re.MULTILINE,
        )

        # Split into blocks per geo step (each outer SCF starts a new block)
        blocks = re.split(r"outer SCF iter\s*=\s*\d+", content)
        # Last block = current geo step's SCF
        target_content = blocks[-1] if blocks else content

        ot_matches = ot_pattern.findall(target_content)
        if not ot_matches:
            # Try on full content
            ot_matches = ot_pattern.findall(content)

        for m in ot_matches:
            cycle_num = int(m[0])
            try:
                energy = float(m[4])  # total energy
            except (ValueError, OverflowError):
                continue
            try:
                de = abs(float(m[5]))  # delta E
            except (ValueError, OverflowError):
                de = None

            delta_e = abs(energy - cycles[-1].energy) if cycles else (de if de else None)
            cycles.append(SCFCycle(cycle=cycle_num, energy=energy, delta_e=delta_e))

        # Try diagonalization format as fallback
        if not cycles:
            diag_pattern = re.compile(
                r"^\s*\d+\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+E[+\-]\d+)\s+(\d+\.\d+E[+\-]\d+)",
                re.MULTILINE,
            )
            diag_matches = diag_pattern.findall(content)
            for i, (energy_str, de_str, rms_str) in enumerate(diag_matches, 1):
                try:
                    energy = float(energy_str)
                except (ValueError, OverflowError):
                    continue
                delta_e = abs(energy - cycles[-1].energy) if cycles else None
                cycles.append(SCFCycle(cycle=i, energy=energy, delta_e=delta_e))

        # Check convergence status
        if "SCF run converged" in target_content:
            if cycles:
                # Mark last cycle as converged
                pass  # handled by analyze_scf_convergence

        # Outer SCF convergence
        outer_converged = "outer SCF loop converged" in target_content or \
                          "outer SCF loop converged" in content

        return cycles

    def _extract_geo_steps(self, content: str) -> list:
        """Extract geometry optimization steps from CP2K output.

        Key markers in real CP2K output:
        - "OPT| Step number" marks each geometry optimization step
        - "ENERGY| Total FORCE_EVAL ( QS ) energy [hartree]" gives the energy
        - "outer SCF loop converged" marks SCF completion for that step

        Also extracts:
        - "Informations at step =  N" (older CP2K format)
        """
        steps = []

        # Method 1: Use ENERGY| lines (most reliable for newer CP2K)
        energy_pattern = re.compile(
            r"ENERGY\|\s+Total FORCE_EVAL\s+\(\s*QS\s*\)\s+energy\s+\[hartree\]\s+([-]?\d+\.\d+)",
            re.IGNORECASE,
        )
        energies = energy_pattern.findall(content)

        if energies:
            for i, energy_str in enumerate(energies, 1):
                energy = float(energy_str)
                delta_e = abs(energy - steps[-1].energy) if steps else None
                step = GeoStep(step=i, energy=energy, delta_e=delta_e)
                steps.append(step)

            # Try to get RMS force from OPT| output
            opt_sections = re.split(r"OPT\|\s*\*+\s*\n", content)
            for i, section in enumerate(opt_sections):
                if i == 0 or i > len(steps):
                    continue
                # RMS gradient often reported near OPT section
                rms_match = re.search(
                    r"RMS gradient\s*=\s*(\d+\.?\d*E?[+\-]?\d*)",
                    section,
                )
                max_match = re.search(
                    r"Max gradient\s*=\s*(\d+\.?\d*E?[+\-]?\d*)",
                    section,
                )
                if rms_match and i - 1 < len(steps):
                    steps[i - 1].rms_force = float(rms_match.group(1))
                if max_match and i - 1 < len(steps):
                    steps[i - 1].max_force = float(max_match.group(1))

            # Check for convergence
            if "GEOMETRY OPTIMIZATION COMPLETED" in content or \
               "OPTIMIZATION COMPLETED" in content:
                if steps:
                    steps[-1].converged = True

            return steps

        # Method 2: Older CP2K format with "Informations at step"
        step_blocks = re.split(
            r"--------\s+Informations at step\s+=\s+(\d+)\s+-----------",
            content,
        )
        for i in range(1, len(step_blocks), 2):
            if i + 1 >= len(step_blocks):
                break

            step_num = int(step_blocks[i])
            block = step_blocks[i + 1]

            energy = None
            en_match = re.search(
                r"(?:Total Energy::|ENERGY\| Total FORCE_EVAL.*?:\s*)\s*([-]?\d+\.\d+)",
                block,
            )
            if en_match:
                energy = float(en_match.group(1))
            if energy is None:
                continue

            delta_e = abs(energy - steps[-1].energy) if steps else None
            step = GeoStep(step=step_num, energy=energy, delta_e=delta_e)

            rms_match = re.search(r"RMS gradient\s*[:=]\s*(\d+\.\d+)", block)
            max_match = re.search(r"Max gradient\s*[:=]\s*(\d+\.\d+)", block)
            if rms_match:
                step.rms_force = float(rms_match.group(1))
            if max_match:
                step.max_force = float(max_match.group(1))

            steps.append(step)

        if "GEOMETRY OPTIMIZATION COMPLETED" in content:
            if steps:
                steps[-1].converged = True

        return steps

    def _extract_final_energy(self, content: str) -> float | None:
        m = re.search(r"ENERGY\| Total FORCE_EVAL.*?:\s*([-]?\d+\.\d+)", content)
        if m:
            return float(m.group(1))

        # Fallback
        energies = re.findall(r"Total Energy::\s*([-]?\d+\.\d+)", content)
        if energies:
            return float(energies[-1])

        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract elapsed time from CP2K output."""
        # CP2K end-of-run timing
        m = re.search(
            r"CP2K\s+\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+\s+(\d+\.\d+)",
            content,
        )
        if m:
            return float(m.group(1))

        # Wall time at end
        m = re.search(r"Total wall time\s*:\s*(\d+\.?\d*)", content, re.IGNORECASE)
        if m:
            return float(m.group(1))

        return None

    def _get_outer_scf_info(self, content: str) -> dict:
        """Extract outer SCF convergence info."""
        info = {"outer_iterations": 0, "total_inner_steps": 0, "converged": False}

        outer_iters = re.findall(r"outer SCF iter\s*=\s*(\d+)", content)
        if outer_iters:
            info["outer_iterations"] = int(outer_iters[-1])

        conv_match = re.search(
            r"outer SCF loop converged in\s+(\d+)\s+iterations?\s+or\s+(\d+)\s+steps",
            content,
        )
        if conv_match:
            info["converged"] = True
            info["outer_iterations"] = int(conv_match.group(1))
            info["total_inner_steps"] = int(conv_match.group(2))

        return info

    def _extract_errors(self, content: str) -> list:
        errors = []

        patterns = [
            (r"SCF run NOT converged", "SCF not converged"),
            (r"GEOMETRY OPTIMIZATION.*?NOT converged", "Geometry optimization did not converge"),
            (r"Numerical problems", "Numerical issues detected — check initial geometry or basis"),
            (r"Cholesky decompose failed", "Cholesky decomposition failed — SCF unstable"),
            (r"Error in constraints", "Constraint error — check fixed atom definitions"),
            (r"Out of memory", "Out of memory — reduce system size or use smaller basis"),
            (r"Basis set not found", "Basis set file not found"),
            (r"Pseudopotential not found", "Pseudopotential/GTH parameter not found"),
            (r"Maximum number of SCF steps exceeded", "Max SCF steps exceeded — not converging"),
            (r"Too many inner SCF steps", "Inner SCF loop not converging"),
            (r"Error while reading input", "Input file syntax error"),
        ]

        for pattern, msg in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(msg)

        return errors

    def _extract_warnings(self, content: str) -> list:
        warnings = []

        patterns = [
            (r"WARNING.*?SCF.*?slow", "SCF converging slowly"),
            (r"WARNING.*?Poor conditioning", "Poor matrix conditioning — results may have numerical noise"),
            (r"WARNING.*?linear dependence", "Linear dependence in basis detected"),
            (r"WARNING.*?small HOMO-LUMO gap", "Very small HOMO-LUMO gap — check electronic structure"),
            (r"WARNING.*?SCF.*?not.*?converged.*?using.*?non-converged", "Using non-converged density — results unreliable"),
        ]

        for pattern, msg in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(msg)

        return warnings
