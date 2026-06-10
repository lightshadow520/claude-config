"""ML potential output parser.

Handles output from common ML interatomic potentials:
- MACE (Multi-ACE)
- NequIP (e3nn-based)
- CHGNet
- M3GNet
- DeepMD-kit
- ASAP (ASAP-3)
- SevenNet
- ORB
"""

import re
import json
import os
import glob as glob_mod
from .base import BaseParser, ParseResult, SCFCycle, GeoStep, ConvergenceStatus


class MLPotentialParser(BaseParser):
    """Parser for ML potential output files.

    Unlike traditional DFT codes, ML potentials produce:
    - Training logs (loss curves, validation metrics)
    - MD/relaxation logs (energy, forces, steps)
    - LAMMPS-style thermo output (when used as LAMMPS pair style)

    This parser detects the flavor and extracts relevant metrics.
    """

    code = "ml"

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(code=self.code, file_path=file_path, success=False)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
            return result

        # Detect ML flavor
        ml_flavor = self._detect_ml_flavor(content, file_path)
        result.raw_headers["ml_flavor"] = ml_flavor

        # Parse based on flavor
        if ml_flavor == "deepmd":
            result = self._parse_deepmd(result, content)
        elif ml_flavor == "mace":
            result = self._parse_mace(result, content)
        elif ml_flavor == "nequip":
            result = self._parse_nequip(result, content)
        elif ml_flavor == "chgnet":
            result = self._parse_chgnet(result, content)
        elif ml_flavor == "m3gnet":
            result = self._parse_m3gnet(result, content)
        elif ml_flavor == "asap":
            result = self._parse_asap(result, content)
        elif ml_flavor == "lammps_ml":
            result = self._parse_lammps_ml(result, content, file_path)
        else:
            # Generic: try to find energy values and convergence
            result = self._parse_generic_ml(result, content)

        # Errors and warnings
        result.errors = self._extract_errors(content, ml_flavor)
        result.warnings = self._extract_warnings(content)
        result.elapsed_time_seconds = self._extract_elapsed_time(content)

        result.success = self._check_success(content, ml_flavor)

        return result

    def _detect_ml_flavor(self, content: str, file_path: str) -> str:
        """Detect which ML potential was used."""
        basename = os.path.basename(file_path).lower()

        if "model.ckpt" in content or "deepmd" in content.lower():
            return "deepmd"
        if "mace" in content.lower() or "multi-ace" in content.lower():
            return "mace"
        if "nequip" in content.lower() or "e3nn" in content.lower():
            return "nequip"
        if "chgnet" in content.lower():
            return "chgnet"
        if "m3gnet" in content.lower():
            return "m3gnet"
        if "asap" in content.lower() or "asap3" in content.lower():
            return "asap"
        if "lammps" in content.lower() or "pair_style" in content:
            return "lammps_ml"
        if basename.endswith(".csv") or basename.endswith(".log"):
            return "generic"

        return "unknown"

    def _parse_deepmd(self, result: ParseResult, content: str) -> ParseResult:
        """Parse DeepMD-kit training log (lcurve.out or .log).

        Format (lcurve.out):
        # step      rmse_val    rmse_trn    rmse_e_val  rmse_e_trn  rmse_f_val  rmse_f_trn
              0      1.23e-01    1.34e-01    1.23e-02    1.34e-02    9.87e-02    1.00e-01
            ...
        """
        cycles = []

        # lcurve.out: step + 6 columns (energy + force RMSE for train/val)
        lcurve_pattern = re.compile(
            r"^\s*(\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)\s+(\d+\.?\d*[eE][+\-]?\d+)",
            re.MULTILINE,
        )

        for m in lcurve_pattern.finditer(content):
            step = int(m.group(1))
            # Use validation RMSE as "energy" metric (lower is better)
            rmse_total = float(m.group(2))
            # For convergence: use the decreasing RMSE
            cycles.append(SCFCycle(cycle=step, energy=rmse_total))

        result.scf_cycles = cycles

        if cycles and len(cycles) >= 5:
            # Training is converging if RMSE is decreasing
            recent = [c.energy for c in cycles[-20:]] if len(cycles) >= 20 else [c.energy for c in cycles]
            if recent[-1] < recent[0]:
                result.scf_status = ConvergenceStatus.CONVERGING
                result.raw_headers["training_progress"] = "improving"
            elif abs(recent[-1] - recent[0]) / max(abs(recent[0]), 1e-10) < 0.01:
                result.scf_status = ConvergenceStatus.CONVERGED
                result.raw_headers["training_progress"] = "converged"
            else:
                result.raw_headers["training_progress"] = "not_improving"

            # Store final RMSE
            result.final_energy = cycles[-1].energy
            result.final_energy_units = "RMSE (eV/A for forces)"

        # Extract step count from training
        nsteps = re.search(r"stop_batch\s*=\s*(\d+)", content) or re.search(
            r"numb_steps\s*=\s*(\d+)", content
        )
        if nsteps:
            result.raw_headers["total_training_steps"] = int(nsteps.group(1))

        return result

    def _parse_mace(self, result: ParseResult, content: str) -> ParseResult:
        """Parse MACE training log.

        MACE logs typically have:
        - Epoch-based loss reporting
        - E/w: energy RMSE per atom (meV)
        - F/w: force RMSE (meV/A)
        """
        cycles = []

        # Epoch-based loss
        loss_pattern = re.compile(
            r"(?:Epoch|Step)\s+(\d+).*?loss\s*[=:]\s*(\d+\.?\d*[eE]?[+\-]?\d*)",
            re.IGNORECASE,
        )

        for m in loss_pattern.finditer(content):
            epoch = int(m.group(1))
            loss = float(m.group(2))
            cycles.append(SCFCycle(cycle=epoch, energy=loss))

        if not cycles:
            # Try extracting validation RMSE energy/force values
            rmse_pattern = re.compile(
                r"Step\s+(\d+).*?E_(\w+).*?([-]?\d+\.?\d*[eE]?[+\-]?\d*).*?"
                r"F_(\w+).*?([-]?\d+\.?\d*[eE]?[+\-]?\d*)",
                re.IGNORECASE,
            )
            for m in rmse_pattern.finditer(content):
                step = int(m.group(1))
                # Use a combined metric
                try:
                    e_val = float(m.group(3))
                    f_val = float(m.group(5))
                    combined = (e_val ** 2 + f_val ** 2) ** 0.5
                except (ValueError, IndexError):
                    continue
                cycles.append(SCFCycle(cycle=step, energy=combined))

        result.scf_cycles = cycles
        if cycles and len(cycles) >= 5:
            recent = [c.energy for c in cycles[-10:]]
            if recent[-1] < recent[0] * 0.95:
                result.scf_status = ConvergenceStatus.CONVERGING

        return result

    def _parse_nequip(self, result: ParseResult, content: str) -> ParseResult:
        """Parse NequIP training log (CSV or tensorboard-style)."""
        # NequIP typically outputs CSV: epoch,train_loss,val_loss,...
        cycles = []

        # Try CSV format
        lines = content.strip().split("\n")
        header = None
        data_start = 0

        for i, line in enumerate(lines):
            if "epoch" in line.lower() or "step" in line.lower():
                header = line.lower().split(",")
                data_start = i + 1
                break

        if header:
            # Find relevant columns
            epoch_col = None
            val_loss_col = None
            train_loss_col = None

            for j, col in enumerate(header):
                col_clean = col.strip()
                if col_clean in ("epoch", "step", "training_step"):
                    epoch_col = j
                elif "val" in col_clean and ("loss" in col_clean or "rmse" in col_clean):
                    val_loss_col = j
                elif "train" in col_clean and ("loss" in col_clean or "rmse" in col_clean):
                    train_loss_col = j

            if epoch_col is not None and (val_loss_col is not None or train_loss_col is not None):
                loss_col = val_loss_col if val_loss_col is not None else train_loss_col
                for line in lines[data_start:]:
                    try:
                        parts = line.strip().split(",")
                        if len(parts) > max(epoch_col, loss_col):
                            epoch = int(float(parts[epoch_col]))
                            loss = float(parts[loss_col])
                            cycles.append(SCFCycle(cycle=epoch, energy=loss))
                    except (ValueError, IndexError):
                        continue

        result.scf_cycles = cycles
        if cycles:
            result.raw_headers["final_loss"] = cycles[-1].energy

        return result

    def _parse_chgnet(self, result: ParseResult, content: str) -> ParseResult:
        """Parse CHGNet output (relaxation or MD log).

        CHGNet is typically used through ASE or pymatgen.
        Output looks like:
        Step  Energy(eV)  ForceMax  ...
        """
        cycles = []

        step_pattern = re.compile(
            r"Step\s+(\d+)\s+([-]?\d+\.?\d*)\s+(\d+\.?\d*[eE]?[+\-]?\d*)",
            re.IGNORECASE,
        )

        for m in step_pattern.finditer(content):
            step = int(m.group(1))
            energy = float(m.group(2))
            force = float(m.group(3))
            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=step, energy=energy, delta_e=delta_e, rms_density=force))

        result.scf_cycles = cycles

        if cycles and len(cycles) >= 3:
            recent = [c.energy for c in cycles[-5:]] if len(cycles) >= 5 else [c.energy for c in cycles]
            en_changes = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
            if en_changes and max(en_changes) < 1e-3:
                result.scf_status = ConvergenceStatus.CONVERGED
            elif all(f is not None and f < 1e-2 for f in [c.rms_density for c in cycles[-3:]] if c.rms_density):
                result.scf_status = ConvergenceStatus.CONVERGED
            else:
                result.scf_status = ConvergenceStatus.CONVERGING

        result.final_energy = cycles[-1].energy if cycles else None
        result.final_energy_units = "eV"

        return result

    def _parse_m3gnet(self, result: ParseResult, content: str) -> ParseResult:
        """Parse M3GNet relaxation output."""
        # Similar to CHGNet — ASE-based optimization
        return self._parse_chgnet(result, content)

    def _parse_asap(self, result: ParseResult, content: str) -> ParseResult:
        """Parse ASAP-3 relaxation log."""
        cycles = []

        # ASE-style optimizer output
        step_pattern = re.compile(
            r"(?:Step|BFGS)\s+(\d+).*?energy[=\s]+([-]?\d+\.?\d*)",
            re.IGNORECASE,
        )

        for m in step_pattern.finditer(content):
            step = int(m.group(1))
            energy = float(m.group(2))
            delta_e = abs(energy - cycles[-1].energy) if cycles else None
            cycles.append(SCFCycle(cycle=step, energy=energy, delta_e=delta_e))

        result.scf_cycles = cycles
        if cycles:
            result.final_energy = cycles[-1].energy
            result.final_energy_units = "eV"

        return result

    def _parse_lammps_ml(self, result: ParseResult, content: str, file_path: str) -> ParseResult:
        """Parse ML potential used as LAMMPS pair style.

        Detect from log.lammps or similar.
        """
        # Use LAMMPS parser for the thermo output
        from .lammps import LAMMPSParser

        lmp = LAMMPSParser()
        lmp_result = lmp.parse(file_path)

        result.scf_cycles = lmp_result.scf_cycles
        result.scf_status = lmp_result.scf_status
        result.final_energy = lmp_result.final_energy
        result.elapsed_time_seconds = lmp_result.elapsed_time_seconds
        result.warnings = lmp_result.warnings
        result.errors = lmp_result.errors
        result.raw_headers.update(lmp_result.raw_headers)

        return result

    def _parse_generic_ml(self, result: ParseResult, content: str) -> ParseResult:
        """Generic fallback for ML output."""
        # Try to identify step + energy patterns
        cycles = []

        # Common pattern: step/epoch + loss/energy value
        generic_patterns = [
            (r"(?:Step|Epoch|Iteration)\s*[:=]?\s*(\d+).*?(?:Energy|Loss|RMSE)\s*[:=]?\s*([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)", re.IGNORECASE),
            (r"^\s*(\d+)\s+([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)\s+([-]?\d+\.?\d*(?:[eE][+\-]?\d+)?)", re.MULTILINE),
        ]

        for pattern, flags in [(generic_patterns[0], re.IGNORECASE), (generic_patterns[1], re.MULTILINE)]:
            if cycles:
                break
            for m in re.finditer(pattern, content):
                step = int(m.group(1))
                try:
                    energy = float(m.group(2))
                except (ValueError, OverflowError):
                    continue
                delta_e = abs(energy - cycles[-1].energy) if cycles else None
                cycles.append(SCFCycle(cycle=step, energy=energy, delta_e=delta_e))

        result.scf_cycles = cycles
        if cycles and len(cycles) >= 3:
            recent = [c.energy for c in cycles[-5:]]
            if len(recent) >= 3 and recent[-1] < recent[-2] < recent[-3]:
                result.scf_status = ConvergenceStatus.CONVERGING

        return result

    def _extract_elapsed_time(self, content: str) -> float | None:
        m = re.search(r"(?:Total|Wall|CPU)\s*time\s*[:=]?\s*(\d+\.?\d*)\s*(?:s|sec|seconds?)", content, re.IGNORECASE)
        if m:
            return float(m.group(1))
        m = re.search(r"(\d+):(\d+):(\d+)", content)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        return None

    def _check_success(self, content: str, flavor: str) -> bool:
        success_indicators = {
            "deepmd": "finished training" in content.lower() or "saved model" in content.lower(),
            "mace": "training complete" in content.lower() or "model saved" in content.lower(),
            "nequip": "training complete" in content.lower(),
            "chgnet": "relaxation converged" in content.lower() or "optimization converged" in content.lower(),
        }
        if flavor in success_indicators:
            return success_indicators[flavor]
        return "error" not in content.lower()[:1000]

    def _extract_errors(self, content: str, flavor: str) -> list:
        errors = []

        common_patterns = [
            (r"CUDA out of memory", "GPU out of memory — reduce batch size or model size"),
            (r"nan.*?loss", "NaN in loss — exploding gradients or bad data"),
            (r"inf.*?loss", "Inf in loss — numerical instability"),
            (r"KeyError", "Missing key in data — check dataset format"),
            (r"FileNotFoundError", "Data file not found — check path"),
            (r"ValueError.*?shape", "Shape mismatch — check model/dataset dimensions"),
            (r"assert.*?failed", "Assertion failed — check input data validity"),
            (r"segmentation fault", "Segfault — likely GPU memory or CUDA issue"),
            (r"model.*?not found", "Model checkpoint not found"),
            (r"cannot import", "Missing Python dependency"),
            (r"CUDA error", "CUDA error — GPU issue"),
        ]

        for pattern, msg in common_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(msg)

        # ML-specific error patterns
        ml_specific = {
            "deepmd": [
                (r"type\.raw.*?not found", "DeepMD type.raw file missing"),
                (r"numb_sel.*?exceed", "Sele_a (neighbor count) exceeded — increase sel in model"),
            ],
            "mace": [
                (r"Atomic number.*?not.*?valid", "Invalid atomic number in data"),
                (r"r_max.*?too.*?large", "Cutoff too large for training — reduce r_max"),
            ],
            "chgnet": [
                (r"structure.*?error", "Structure format error — check ASE atoms object"),
                (r"Magmom.*?not", "Magnetic moment initialization issue"),
            ],
        }

        if flavor in ml_specific:
            for pattern, msg in ml_specific[flavor]:
                if re.search(pattern, content, re.IGNORECASE):
                    errors.append(msg)

        return errors

    def _extract_warnings(self, content: str) -> list:
        warnings = []

        patterns = [
            (r"GPU.*?not.*?available", "GPU not detected — running on CPU (slow)"),
            (r"learning rate.*?plateau", "Learning rate plateaued — training may stall"),
            (r"loss.*?not.*?decreasing", "Loss not decreasing — check learning rate or model capacity"),
            (r"validation.*?loss.*?increasing", "Validation loss increasing — possible overfitting"),
            (r"force.*?RMSE.*?>.*?0\.1", "Force RMSE > 0.1 eV/A — model accuracy may be low"),
            (r"energy.*?RMSE.*?>.*?0\.01", "Energy RMSE > 10 meV/atom — accuracy may be insufficient"),
            (r"batch.*?size.*?reduced", "Batch size auto-reduced due to memory"),
        ]

        for pattern, msg in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(msg)

        return warnings
