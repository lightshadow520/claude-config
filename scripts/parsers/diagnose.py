"""Error diagnosis decision tree for computational chemistry.

Checks common root causes systematically, avoiding AI hallucination.
Each check is a deterministic function — no guessing.
"""

import re
from dataclasses import dataclass, field


@dataclass
class DiagnosisResult:
    """Result of a diagnostic check."""
    issue: str
    confidence: str  # 'high', 'medium', 'low'
    evidence: str
    fix: str


def diagnose_geometry(coords_text: str) -> list[DiagnosisResult]:
    """Check geometry for common problems (atom overlap, linear angles, etc.).

    Args:
        coords_text: XYZ/PDB/POSCAR format coordinate text

    Returns:
        List of DiagnosisResult with detected issues
    """
    results = []

    # Parse coordinates
    atoms = _parse_xyz(coords_text)
    if not atoms:
        return [DiagnosisResult(
            issue="Cannot parse coordinates",
            confidence="high",
            evidence="No valid atom coordinates found in input",
            fix="Check format of coordinate file",
        )]

    # Check 1: Atom overlap (< 0.5 Å between any pair)
    import math
    min_dist = float("inf")
    min_pair = None
    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            dx = atoms[i][1] - atoms[j][1]
            dy = atoms[i][2] - atoms[j][2]
            dz = atoms[i][3] - atoms[j][3]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < min_dist:
                min_dist = dist
                min_pair = (atoms[i][0], atoms[j][0], dist)

    if min_dist < 0.5:
        results.append(DiagnosisResult(
            issue=f"ATOM OVERLAP: {min_pair[0]} and {min_pair[1]} are {min_dist:.2f} A apart",
            confidence="high",
            evidence=f"Minimum interatomic distance = {min_dist:.2f} Å (normal bonds >= 0.5 Å)",
            fix="Check initial geometry for overlapping atoms. If from a previous calculation, "
                "the optimization may have pushed atoms together. Try fixing distance constraints "
                "or regenerating the initial structure.",
        ))
    elif min_dist < 0.9:
        results.append(DiagnosisResult(
            issue=f"SUSPICIOUSLY CLOSE ATOMS: {min_pair[0]}-{min_pair[1]} at {min_dist:.2f} Å",
            confidence="medium",
            evidence=f"Distance {min_dist:.2f} Å is shorter than typical bonds",
            fix="Visually inspect the geometry. If intentional (e.g., H-H in H2), ignore.",
        ))

    # Check 2: Linear/near-linear angles (Z-matrix / internal coordinate issues)
    for i in range(1, len(atoms)):
        for j in range(i + 1, len(atoms)):
            for k in range(j + 1, len(atoms)):
                # Vector i->j and j->k
                v1 = (atoms[j][1] - atoms[i][1], atoms[j][2] - atoms[i][2], atoms[j][3] - atoms[i][3])
                v2 = (atoms[k][1] - atoms[j][1], atoms[k][2] - atoms[j][2], atoms[k][3] - atoms[j][3])
                d1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
                d2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
                if d1 < 0.01 or d2 < 0.01:
                    continue
                dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
                cos_angle = dot / (d1 * d2)
                cos_angle = max(-1.0, min(1.0, cos_angle))
                angle = math.degrees(math.acos(cos_angle))
                if angle > 178.0:
                    results.append(DiagnosisResult(
                        issue=f"NEAR-LINEAR ANGLE: {atoms[i][0]}-{atoms[j][0]}-{atoms[k][0]} = {angle:.1f}°",
                        confidence="high" if angle > 179.0 else "medium",
                        evidence=f"Bond angle is {angle:.1f} degrees (dangerously close to 180°)",
                        fix="Near-linear angles cause Z-matrix failures. Use Cartesian coordinates "
                            "instead, or slightly perturb the angle away from 180°.",
                    ))

    # Check 3: Unreasonable bond lengths
    typical_bonds = {
        ("H", "H"): 0.74, ("C", "H"): 1.09, ("C", "C"): 1.54, ("C", "O"): 1.43,
        ("C", "N"): 1.47, ("O", "H"): 0.96, ("N", "H"): 1.01, ("C", "F"): 1.35,
        ("C", "Cl"): 1.77, ("C", "Br"): 1.94, ("O", "O"): 1.48, ("N", "N"): 1.45,
        ("S", "H"): 1.34, ("S", "C"): 1.81, ("S", "O"): 1.43,
    }

    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            dx = atoms[i][1] - atoms[j][1]
            dy = atoms[i][2] - atoms[j][2]
            dz = atoms[i][3] - atoms[j][3]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            elem_pair = tuple(sorted([atoms[i][0], atoms[j][0]]))
            expected = typical_bonds.get(elem_pair)
            if expected and dist > expected * 2.5:
                # Only flag if they're actually supposed to be bonded
                if dist < 3.0:  # Don't flag obvious non-bonds
                    results.append(DiagnosisResult(
                        issue=f"LONG BOND: {atoms[i][0]}-{atoms[j][0]} = {dist:.2f} Å "
                               f"(typical: {expected:.2f} Å)",
                        confidence="low",
                        evidence=f"Distance {dist:.2f} Å vs typical {expected:.2f} Å",
                        fix="Check if these atoms should be bonded. If YES, check initial geometry. "
                            "If NO, this is a non-bonded contact — ignore.",
                    ))

    return results


def diagnose_scf_oscillation(scf_cycles: list, energy_tolerance: float = 1e-6) -> list[DiagnosisResult]:
    """Diagnose SCF oscillation causes.

    Args:
        scf_cycles: list of SCFCycle objects
        energy_tolerance: convergence threshold

    Returns:
        List of DiagnosisResult
    """
    results = []

    if len(scf_cycles) < 5:
        return results

    energies = [c.energy for c in scf_cycles]

    # Check for oscillation pattern
    oscillations = 0
    for i in range(2, len(energies)):
        d1 = energies[i] - energies[i - 1]
        d2 = energies[i - 1] - energies[i - 2]
        if d1 * d2 < 0:
            oscillations += 1

    osc_ratio = oscillations / max(len(energies) - 2, 1)

    if osc_ratio > 0.4:
        # Check if it's charge sloshing
        energy_amplitudes = [abs(energies[i] - energies[i - 1]) for i in range(1, len(energies))]
        max_amplitude = max(energy_amplitudes[-10:]) if len(energy_amplitudes) >= 10 else max(energy_amplitudes)
        avg_amplitude = sum(energy_amplitudes[-10:]) / min(10, len(energy_amplitudes))

        if max_amplitude > 1e-3:
            results.append(DiagnosisResult(
                issue="CHARGE SLOSHING — large SCF energy oscillation (> 1 mHartree)",
                confidence="high",
                evidence=f"Energy oscillation amplitude: {max_amplitude:.2e}, oscillation ratio: {osc_ratio:.0%}",
                fix="1. Use Fermi smearing (Gaussian: add 'int=ultrafine' or smearing; VASP: ISMEAR=1, SIGMA=0.1)\n"
                    "2. Reduce mixing: VASP: AMIX=0.1, BMIX=0.0001; Gaussian: SCF=(MaxCycle=512,Conver=6)\n"
                    "3. Try different SCF algorithm: VASP: ALGO=All or ALGO=Normal\n"
                    "4. For metal/small-gap systems: use smearing always",
            ))
        else:
            results.append(DiagnosisResult(
                issue="MILD SCF OSCILLATION — energy oscillating but amplitudes small",
                confidence="medium",
                evidence=f"Amplitude: {avg_amplitude:.2e}, ratio: {osc_ratio:.0%}",
                fix="Consider slight damping adjustment. If converging (amplitude decreasing), "
                    "just needs more cycles. If not, try DIIS/EDIIS mixing.",
            ))

    # Check for monotonic divergence
    if len(energies) >= 10:
        first_5 = energies[5:10]
        last_5 = energies[-5:]
        first_avg = sum(first_5) / 5
        last_avg = sum(last_5) / 5
        if (last_avg - first_avg) > 0.1:  # Energy going UP significantly
            results.append(DiagnosisResult(
                issue="ENERGY INCREASING MONOTONICALLY — not a variational minimum",
                confidence="high",
                evidence=f"Energy rose from {first_avg:.6f} to {last_avg:.6f}",
                fix="Possible causes:\n"
                    "1. Initial guess wildly wrong — try different initial guess\n"
                    "2. Orbital rotation issue — check for symmetry breaking\n"
                    "3. For metals: use smearing and larger k-mesh\n"
                    "4. Check if charge/multiplicity is correct",
            ))

    return results


def diagnose_geo_optimization_failure(content: str, geo_steps: list) -> list[DiagnosisResult]:
    """Diagnose geometry optimization failures.

    Checks for:
    - Atom overlap causing force explosion
    - Shallow PES (flat potential)
    - Wrong coordinate system
    - Too tight convergence
    """
    results = []

    if not geo_steps or len(geo_steps) < 2:
        return results

    # Check for force explosion
    forces = [s.max_force for s in geo_steps if s.max_force is not None]
    if len(forces) >= 3:
        recent = forces[-3:]
        if len(recent) >= 3 and recent[-1] > recent[0] * 5:
            results.append(DiagnosisResult(
                issue="FORCE EXPLOSION — maximum force increasing rapidly",
                confidence="high",
                evidence=f"Forces: {recent[0]:.2f} → {recent[-1]:.2f}",
                fix="This is usually caused by ATOM OVERLAP — atoms are too close and repelling.\n"
                    "1. Run geometry check first: diagnose_geometry()\n"
                    "2. If overlap confirmed: fix initial geometry before re-running\n"
                    "3. If geometry is fine: try smaller optimization step (reduced trust radius)\n"
                    "4. For soft modes: use different optimizer (e.g., GDIIS instead of BFGS)",
            ))

    # Check for slow convergence (many steps with small improvement)
    energies = [s.energy for s in geo_steps]
    if len(energies) >= 10:
        recent_energy_changes = [abs(energies[i] - energies[i - 1])
                                  for i in range(max(1, len(energies) - 10), len(energies))]
        if all(de < 1e-5 for de in recent_energy_changes):
            results.append(DiagnosisResult(
                issue="SLOW/STUCK OPTIMIZATION — energy barely changing",
                confidence="medium",
                evidence="Energy changes < 1e-5 Hartree for last 10 steps",
                fix="Possible causes:\n"
                    "1. Flat PES region — try different optimizer or add constraints\n"
                    "2. Convergence criteria too tight for this system\n"
                    "3. Near a saddle point — try perturbing along low-frequency mode\n"
                    "4. For large flexible molecules: use redundant internal coordinates",
            ))

    # Check for too many steps
    if len(geo_steps) > 50:
        results.append(DiagnosisResult(
            issue=f"MANY OPTIMIZATION STEPS ({len(geo_steps)}) — may be stuck or inefficient",
            confidence="medium",
            evidence=f"Calculation has run {len(geo_steps)} steps without converging",
            fix="1. Check if optimization is making progress (forces decreasing?)\n"
                "2. If stuck near minimum but not meeting criteria: relax convergence criteria\n"
                "3. If oscillating: try GDIIS or conjugate gradient instead of BFGS\n"
                "4. Consider restarting from current geometry",
        ))

    return results


def diagnose_error(content: str, code: str) -> list[DiagnosisResult]:
    """General error diagnosis based on error keywords.

    Args:
        content: raw output file content
        code: code identifier string

    Returns:
        List of DiagnosisResult with likely root causes
    """
    results = []

    # Memory errors
    if re.search(r"out of memory|memory.*?error|allocation.*?fail|cannot allocate|not enough memory|malloc.*?fail",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="INSUFFICIENT MEMORY",
            confidence="high",
            evidence="Memory allocation error in output",
            fix="1. Reduce basis set size or use ECPs for heavy atoms\n"
                "2. Reduce k-point mesh (VASP) or integration grid\n"
                "3. Use RI approximation (ORCA: !RI or !RIJCOSX)\n"
                "4. Request more memory: Gaussian: %Mem=..., VASP: adjust NCORE/KPAR\n"
                "5. Split job across more nodes/cores",
        ))

    # Disk space
    if re.search(r"no space left|disk.*?full|quota.*?exceed|file.*?too large",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="DISK SPACE EXHAUSTED",
            confidence="high",
            evidence="Disk space/quota error in output",
            fix="1. Delete old WAVECAR/CHGCAR files from previous runs\n"
                "2. Clean scratch/tmp directories\n"
                "3. Use compression flags if available\n"
                "4. Move completed jobs off compute node",
        ))

    # Input file errors
    if re.search(r"unknown keyword|unrecognized|syntax error|input error|Error.*?reading|Error in input",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="INPUT FILE SYNTAX ERROR",
            confidence="high",
            evidence="Unrecognized keyword or syntax error in input",
            fix="1. Check input file against the code manual\n"
                "2. Check for typos in keywords and atom labels\n"
                "3. Verify coordinate format matches the code's expected format\n"
                "4. Check that all required sections are present",
        ))

    # Missing files
    if re.search(r"file.*?not found|cannot open|cannot find|missing.*?file",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="REQUIRED FILE MISSING",
            confidence="high",
            evidence="File-not-found error in output",
            fix="1. Check that all input files are in the run directory\n"
                "2. For VASP: POTCAR, POSCAR, KPOINTS, INCAR all required\n"
                "3. For Gaussian: check %Chk= path and .chk file existence\n"
                "4. Check file permissions",
        ))

    # Convergence failures
    if re.search(r"SCF.*?not.*?converg|convergence.*?fail|exceeded max.*?cycles|maximum.*?scf.*?exceed",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="SCF CONVERGENCE FAILURE",
            confidence="high",
            evidence="SCF did not converge within allowed cycles",
            fix="1. Check initial geometry (atom overlap?)\n"
                "2. Try smearing for metals/small-gap systems\n"
                "3. Reduce SCF mixing parameter\n"
                "4. Try different initial guess\n"
                "5. Increase max SCF cycles\n"
                "6. Check if charge/multiplicity is reasonable",
        ))

    # License errors (common in MS/VASP)
    if re.search(r"license.*?(?:error|fail|check|denied|expired|not.*?valid)",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="LICENSE ERROR",
            confidence="high",
            evidence="License validation error",
            fix="1. Check license server is running\n"
                "2. Verify license file is not expired\n"
                "3. Check network connection to license server\n"
                "4. For floating licenses: check all seats not in use",
        ))

    # Parallel execution errors (MPI)
    if re.search(r"MPI.*?error|mpirun.*?fail|process.*?terminated|SIGSEGV|segmentation fault|signal.*?11",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="PARALLEL EXECUTION ERROR (MPI/SIGNAL)",
            confidence="medium",
            evidence="MPI error or process signal",
            fix="1. Check if the calculation runs with fewer cores\n"
                "2. Memory per core may be insufficient — reduce cores/processes\n"
                "3. Stack size limit: 'ulimit -s unlimited'\n"
                "4. Check MPI library compatibility\n"
                "5. For VASP: check NCORE, KPAR settings",
        ))

    # Code-specific: atom overlap check
    if re.search(r"atoms.*?too.*?close|distance.*?too.*?small|atoms.*?overlap|z-matrix.*?fail|Bend failed",
                 content, re.IGNORECASE):
        results.append(DiagnosisResult(
            issue="ATOM OVERLAP OR CLOSE CONTACT",
            confidence="high",
            evidence="Distance/overlap error detected",
            fix="1. Run coordinate check: diagnose_geometry()\n"
                "2. Check all interatomic distances\n"
                "3. If from previous calculation: the structure may have collapsed\n"
                "4. Regenerate initial geometry or adjust manually",
        ))

    return results


def _parse_xyz(text: str) -> list:
    """Parse XYZ-format coordinates. Returns [(elem, x, y, z), ...]."""
    atoms = []

    # Try POSCAR format
    if "Direct" in text or "Cartesian" in text:
        lines = text.strip().split("\n")
        in_coords = False
        for line in lines:
            if line.strip() == "":
                continue
            if "Direct" in line or "Cartesian" in line:
                in_coords = True
                continue
            if in_coords:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        elem = "X"
                        atoms.append((elem, x, y, z))
                    except ValueError:
                        break
        return atoms

    # Try standard XYZ format
    lines = text.strip().split("\n")
    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            elem = parts[0]
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                atoms.append((elem, x, y, z))
            except ValueError:
                continue

    return atoms
