"""VASP output parser (OUTCAR + OSZICAR)."""

import re
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class VASPParser(BaseParser):
    """Parser for VASP output files.

    Reads OUTCAR for detailed info, OSZICAR for per-iteration energy.
    """

    code = "vasp"
    scf_convergence_threshold = 1e-6  # eV for electronic convergence

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        # file_path can be OUTCAR or a directory
        import os
        if os.path.isdir(file_path):
            outcar_path = os.path.join(file_path, "OUTCAR")
            oszicar_path = os.path.join(file_path, "OSZICAR")
        else:
            outcar_path = file_path
            oszicar_path = os.path.join(os.path.dirname(file_path), "OSZICAR")

        # Read OUTCAR
        try:
            with open(outcar_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"OUTCAR not found: {outcar_path}")
            content = ""

        # Read OSZICAR for per-iteration energies
        oszicar_content = ""
        try:
            with open(oszicar_path, "r", encoding="utf-8", errors="replace") as f:
                oszicar_content = f.read()
        except FileNotFoundError:
            pass

        # Extract SCF cycles from OSZICAR (per electronic iteration)
        result.scf_cycles = self._extract_scf_from_oszicar(oszicar_content)

        # Extract geometry optimization steps from OUTCAR
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

        # Final energy from OUTCAR
        result.final_energy = self._extract_final_energy(content)
        result.final_energy_units = "eV"

        # Elapsed time
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        # Check if run completed
        result.success = "General timing and accounting" in content

        return result

    def _extract_scf_from_oszicar(self, content: str) -> list:
        """Extract SCF iterations from OSZICAR.

        Format:
              N       E                     dE             d eps       ncg     rms          rms(c)
        DAV:   1    -0.123456789000E+03   -0.12345E+03   -0.23456E+04  12   0.345E+02
        DAV:   2    -0.123456789123E+03   -0.12345E-06   -0.23456E-08  12   0.345E-03
        ...
        """
        cycles = []

        # Match DAV/RMM iterations
        iter_pattern = re.compile(
            r"(?:DAV|RMM):\s+(\d+)\s+([-]?[0-9.E+\-]+)\s+([-]?[0-9.E+\-]+)",
        )
        matches = iter_pattern.findall(content)

        for m in matches:
            cycle_num = int(m[0])
            try:
                energy = float(m[1])
            except (ValueError, OverflowError):
                continue
            try:
                de = abs(float(m[2]))
            except (ValueError, OverflowError):
                de = None

            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=cycle_num, energy=energy, delta_e=delta_e))

        return cycles

    def _extract_geo_steps(self, content: str) -> list:
        """Extract geometry optimization steps from OUTCAR.

        VASP prints energy at each ionic step.
        Key markers:
        - "FREE ENERGIE OF THE ION-ELECTRON SYSTEM" or "free energy    TOTEN"
        - "reached required accuracy" for convergence
        """
        steps = []

        # Find total energy at each ionic step
        # VASP 5.x: "FREE ENERGIE OF THE ION-ELECTRON SYSTEM"
        # VASP 6.x: "free energy    TOTEN  ="
        energy_blocks = re.split(
            r"FREE ENERGIE OF THE ION-ELECTRON SYSTEM|free energy\s+TOTEN\s+=",
            content,
        )

        # Find each ionic step's final energy
        # Pattern near the end of each SCF block
        energy_pattern = re.compile(
            r"(?:FREE ENERGIE OF THE ION-ELECTRON SYSTEM|free  energy\s+TOTEN\s+=\s+([-]?\d+\.\d+)\s+eV)",
        )
        energies = energy_pattern.findall(content)

        # Also look for "energy(sigma->0)"
        sigma_pattern = re.compile(
            r"energy\s*without entropy\s*=\s*([-]?\d+\.\d+)\s+energy\(sigma->0\)\s*=\s*([-]?\d+\.\d+)",
        )
        sigma_energies = sigma_pattern.findall(content)

        # Use sigma->0 energies if available, otherwise TOTEN
        if sigma_energies:
            energies = [e[1] for e in sigma_energies]

        for i, energy_str in enumerate(energies, 1):
            energy = float(energy_str)
            delta_e = abs(energy - steps[-1].energy) if steps else None
            steps.append(GeoStep(step=i, energy=energy, delta_e=delta_e))

        # Extract forces from OUTCAR
        force_blocks = re.split(r"POSITION\s+TOTAL-FORCE\s+\(eV/Angst\)", content)
        for i, block in enumerate(force_blocks[1:], 1):
            if i <= len(steps):
                # Extract RMS force from OUTCAR
                rms_match = re.search(
                    r"FORCES: max atom, RMS\s+([-]?\d+\.\d+)\s+([-]?\d+\.\d+)",
                    block,
                )
                if rms_match:
                    steps[i - 1].max_force = abs(float(rms_match.group(1)))
                    steps[i - 1].rms_force = abs(float(rms_match.group(2)))

        # Check for ionic convergence
        # "reached required accuracy - stopping structural energy minimisation"
        conv_blocks = content.split("reached required accuracy")
        for i, step in enumerate(steps):
            # A step is converged if "reached required accuracy" appears after it
            pass
        if "reached required accuracy" in content:
            if steps:
                steps[-1].converged = True

        return steps

    def _extract_final_energy(self, content: str) -> float | None:
        """Extract final energy from OUTCAR (in eV)."""
        # Try sigma->0 energy first (most accurate)
        m = re.search(
            r"energy\(sigma->0\)\s*=\s*([-]?\d+\.\d+)",
            content,
        )
        if m:
            return float(m.group(1))

        # Fallback: TOTEN
        toten_matches = re.findall(
            r"free\s+energy\s+TOTEN\s+=\s+([-]?\d+\.\d+)\s+eV",
            content,
        )
        if toten_matches:
            return float(toten_matches[-1])

        return None

    def _extract_elapsed_time(self, content: str) -> float | None:
        """Extract elapsed time from OUTCAR."""
        # VASP prints timing at the end
        m = re.search(
            r"Total CPU time used \(sec\):\s+(\d+\.?\d*)",
            content,
        )
        if m:
            return float(m.group(1))

        # Alternative: Elapsed time
        m = re.search(
            r"Elapsed time \(sec\):\s+(\d+\.?\d*)",
            content,
        )
        if m:
            return float(m.group(1))

        return None

    def _extract_errors(self, content: str) -> list:
        """Extract error patterns from VASP output."""
        errors = []

        error_patterns = [
            (r"WARNING: Sub-Space-Matrix is not hermitian", "Sub-space matrix not Hermitian — try ALGO=Normal or increase NBANDS"),
            (r"VERY BAD NEWS.*?internal error", "VASP internal error — check input files and memory"),
            (r"ERROR FEXCP", "Exchange-correlation error — check POTCAR/GGA tag compatibility"),
            (r"ERROR.*?the linear tetrahedron method.*?not enough k-points", "Not enough k-points for tetrahedron method — use ISMEAR >= 0"),
            (r"POSCAR.*?not found", "POSCAR file not found or unreadable"),
            (r"POTCAR.*?not found", "POTCAR missing or element mismatch with POSCAR"),
            (r"incorrect EDIFF", "EDIFF value too small or unreasonable"),
            (r"Fatal error", "VASP fatal error — see details above this line"),
            (r"BRMIX.*?very serious problems", "Charge density mixing failure — try different ALGO or AMIX/BMIX"),
            (r"ZBRENT.*?fatal error.*?could not locate minimum", "Electronic minimization stuck — try ALGO=All or adjust mixing"),
            (r"ZPOTRF.*?not enough memory", "LAPACK memory error — reduce KPAR or system size"),
            (r"SGRCON.*?small quotient", "SCF convergence issue — algorithm struggling"),
            (r"EDWAV.*?internal error", "Wavefunction-related error — delete WAVECAR and restart"),
            (r"WARNING.*?DENTET", "Density matrix issue — electronic structure may be problematic"),
        ]

        for pattern, msg in error_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(msg)

        return errors

    def _extract_warnings(self, content: str) -> list:
        """Extract warnings from VASP output."""
        warnings = []

        warning_patterns = [
            (r"WARNING.*?not enough memory", "Memory warning — consider smaller NCORE or fewer KPAR"),
            (r"WARNING.*?charge density.*?negative", "Negative charge density — check POTCAR/geometry"),
            (r"WARNING.*?DENTET", "Electronic convergence may be problematic"),
            (r"Screened.*?exchange.*?slow", "Hartree-Fock part is slow — consider PRECFOCK tuning"),
            (r"dimension of the Fock matrix.*?large", "Large Fock matrix — hybrid functional may be slow"),
            (r"WARNING: random wavefunctions", "Random wavefunctions used — might be slow to converge"),
            (r"ku and kv.*?not equal", "k-point symmetry issue — check KPOINTS/ISYM settings"),
        ]

        for pattern, msg in warning_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(msg)

        return warnings

    @staticmethod
    def detect_calculation_type(content: str) -> str:
        """Detect VASP calculation type from INCAR tags."""
        incar_match = re.search(r"INCAR:(.+?)(?:\n\s*\n|$)", content, re.DOTALL)
        if incar_match:
            incar = incar_match.group(1)
        else:
            return "Unknown"

        if re.search(r"IBRION\s*=\s*[-\d]*[012]", incar):
            if re.search(r"ISIF\s*=\s*3", incar):
                return "Full Relaxation (cell + ions)"
            return "Ionic Relaxation"
        if re.search(r"IBRION\s*=\s*5", incar):
            return "Frequency / Hessian"
        if re.search(r"IBRION\s*=\s*6", incar):
            return "Elastic Constants"
        if re.search(r"IBRION\s*=\s*[78]", incar):
            return "MD / NEB"
        if re.search(r"IBRION\s*=\s*-1", incar):
            return "Single Point (no update)"
        if re.search(r"NSW\s*=\s*0", incar):
            return "Single Point Energy"
        return "Unknown"
