#!/usr/bin/env python3
"""
Remote Linux process inspector via SSH/paramiko.
Produces structured, categorized process lists to avoid context overload.
Categorizes into: computing tasks, zombies, high-load, system/idle.

Usage:
  python remote_ps.py --host <host>                        # overview
  python remote_ps.py --host <host> --diagnose             # flag zombies, contention
  python remote_ps.py --host <host> --json                 # structured data
  python remote_ps.py --host <host> --port <port> --user <user> --key-file <key>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from collections import defaultdict

# ── Calculation software patterns ──────────────────────────────────────────
CALC_PATTERNS = [
    r'vasp_(std|gam|ncl)',
    r'cp2k\.(psmp|popt|sopt|ssmp)',
    r'\bg09\b', r'\bg16\b', r'\bgaussian\b',
    r'^orca\b', r'orca_[a-z]+',
    r'lmp_(mpi|serial)',
    r'(gmx_mpi|mdrun|mdrun_mpi)',
    r'(sander|pmemd)\.',
    r'(pw\.x|cp\.x|ph\.x|neb\.x|projwfc\.x|bands\.x|dynmat\.x|q2r\.x|matdyn\.x)',
    r'castep',
    r'molpro',
    r'(nwchem)',
    r'(siesta)',
    r'(abinit)',
    r'\bdl_poly\b',
    r'\b(lmp|lammps)\b',
    r'python.*\.py',  # likely a compute script
]

KNOWN_TOOLS = {
    'vasp_std': 'VASP',
    'vasp_gam': 'VASP (gamma)',
    'vasp_ncl': 'VASP (NCL)',
    'cp2k.psmp': 'CP2K (MPI)',
    'cp2k.popt': 'CP2K (OpenMP)',
    'cp2k.sopt': 'CP2K (serial)',
    'cp2k.ssmp': 'CP2K (hybrid)',
    'g09': 'Gaussian 09',
    'g16': 'Gaussian 16',
    'mdrun': 'GROMACS',
    'mdrun_mpi': 'GROMACS (MPI)',
    'gmx_mpi': 'GROMACS',
    'lmp_mpi': 'LAMMPS (MPI)',
    'lmp_serial': 'LAMMPS',
    'lmp': 'LAMMPS',
    'pw.x': 'Quantum ESPRESSO (PW)',
    'cp.x': 'Quantum ESPRESSO (CP)',
    'ph.x': 'Quantum ESPRESSO (PH)',
    'neb.x': 'Quantum ESPRESSO (NEB)',
    'castep': 'CASTEP',
    'molpro': 'Molpro',
    'nwchem': 'NWChem',
    'orca': 'ORCA',
    'sander': 'AMBER',
    'siesta': 'SIESTA',
    'abinit': 'ABINIT',
}


def classify_cmd(cmd):
    """Return (is_calc, human_label) for a process command."""
    exe = cmd.split()[0].split('/')[-1] if cmd else ''
    for pattern in CALC_PATTERNS:
        m = re.search(pattern, cmd, re.IGNORECASE)
        if m:
            label = KNOWN_TOOLS.get(exe, exe)
            return True, label
    return False, exe


def parse_ps(raw_output):
    """Parse ps aux output into categorized dict."""
    lines = raw_output.strip().split('\n')
    if not lines:
        return _empty_result()

    processes = []
    for line in lines[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        try:
            proc = {
                'user': parts[0],
                'pid': int(parts[1]),
                'cpu': float(parts[2]),
                'mem': float(parts[3]),
                'vsz': int(parts[4]),
                'rss': int(parts[5]),
                'tty': parts[6],
                'stat': parts[7],
                'start': parts[8],
                'time': parts[9],
                'cmd': parts[10],
            }
        except (ValueError, IndexError):
            continue
        processes.append(proc)

    computing, zombie, high_load, other = [], [], [], []

    for p in processes:
        if 'Z' in p['stat']:
            zombie.append(p)
            continue
        is_calc, label = classify_cmd(p['cmd'])
        if is_calc:
            p['_label'] = label
            computing.append(p)
        elif p['cpu'] >= 80.0 or p['mem'] >= 30.0:
            high_load.append(p)
        else:
            other.append(p)

    # Group other by exe name
    groups = defaultdict(list)
    for p in other:
        exe = p['cmd'].split()[0].split('/')[-1][:25]
        groups[exe].append(p)

    return {
        'computing': computing,
        'zombie': zombie,
        'high_load': high_load,
        'other': other,
        'other_groups': dict(groups),
        'total': len(processes),
    }


def _empty_result():
    return {
        'computing': [], 'zombie': [], 'high_load': [],
        'other': [], 'other_groups': {}, 'total': 0,
    }


# ── Formatting ──────────────────────────────────────────────────────────────

def format_report(parsed, host, user, port):
    """Human-readable structured report."""
    G = '\033[1;32m'  # green
    Y = '\033[1;33m'  # yellow
    R = '\033[1;31m'  # red
    W = '\033[1;37m'  # white
    X = '\033[0m'     # reset
    B = '\033[1;36m'  # cyan

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out = []
    out.append(f"{B}{'='*64}{X}")
    out.append(f"  {B}Process Report:{X} {user}@{host}:{port}  |  {now}")
    out.append(f"{B}{'='*64}{X}")
    out.append("")

    # Computing
    comp = parsed['computing']
    out.append(f"  {G}Computing tasks ({len(comp)} running){X}")
    if comp:
        out.append(f"  {'PID':<8} {'CPU%':<7} {'MEM%':<7} {'TIME':<11} {'TOOL':<20} {'CMD'}")
        out.append(f"  {'-'*8} {'-'*7} {'-'*7} {'-'*11} {'-'*20} {'-'*30}")
        for p in comp:
            label = p.get('_label', '?')
            out.append(f"  {p['pid']:<8} {p['cpu']:<7.1f} {p['mem']:<7.1f} {p['time']:<11} {label:<20} {p['cmd'][:50]}")
    else:
        out.append("  (none)")
    out.append("")

    # Zombies
    zomb = parsed['zombie']
    if zomb:
        out.append(f"  {Y}Zombie / defunct ({len(zomb)}){X}")
        out.append(f"  {'PID':<8} {'STAT':<6} {'CMD'}")
        out.append(f"  {'-'*8} {'-'*6} {'-'*40}")
        for p in zomb:
            out.append(f"  {p['pid']:<8} {p['stat']:<6} {p['cmd'][:60]}")
        out.append("")

    # High load
    high = parsed['high_load']
    if high:
        out.append(f"  {R}High-resource (CPU>80% or MEM>30%) ({len(high)}){X}")
        out.append(f"  {'PID':<8} {'CPU%':<7} {'MEM%':<7} {'CMD'}")
        out.append(f"  {'-'*8} {'-'*7} {'-'*7} {'-'*40}")
        for p in high:
            out.append(f"  {p['pid']:<8} {p['cpu']:<7.1f} {p['mem']:<7.1f} {p['cmd'][:60]}")
        out.append("")

    # System / idle (grouped)
    groups = parsed.get('other_groups', {})
    n_other = parsed['total'] - len(comp) - len(zomb) - len(high)
    if groups:
        sorted_g = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
        out.append(f"  {W}System / idle ({n_other} processes){X}")
        out.append(f"  {'EXE':<24} {'COUNT':<6} {'CPU%':<10} {'MEM%':<10}")
        out.append(f"  {'-'*24} {'-'*6} {'-'*10} {'-'*10}")
        shown = sorted_g[:25]
        for exe, procs in shown:
            cpu_sum = sum(p['cpu'] for p in procs)
            mem_sum = sum(p['mem'] for p in procs)
            out.append(f"  {exe:<24} {len(procs):<6} {cpu_sum:<10.1f} {mem_sum:<10.1f}")
        if len(sorted_g) > 25:
            out.append(f"  ... +{len(sorted_g) - 25} more groups")
        out.append("")

    # Summary line
    out.append(f"  {'─'*64}")
    out.append(f"  Total: {parsed['total']}  |  Compute: {len(comp)}  |  "
               f"Zombie: {len(zomb)}  |  High-load: {len(high)}  |  "
               f"Other: {n_other}")

    return '\n'.join(out)


def diagnose(parsed):
    """Return (issues, warnings) lists for flagged problems."""
    issues, warns = [], []
    comp = parsed['computing']
    zomb = parsed['zombie']
    high = parsed['high_load']

    if zomb:
        issues.append(f"{len(zomb)} zombie process(es) found")
        if len(zomb) > 10:
            issues.append(f"High zombie count ({len(zomb)}) — parent may not be reaping children")

    if not comp:
        warns.append("No calculation processes detected on this server")

    heavy_cpu = [p for p in list(comp) + list(high) if p['cpu'] > 50]
    if len(heavy_cpu) > 1:
        issues.append(f"{len(heavy_cpu)} processes competing for >50% CPU — resource contention likely")
        for p in heavy_cpu:
            issues.append(f"  PID {p['pid']}: {p['cpu']:.0f}% CPU — {p['cmd'].split()[0].split('/')[-1]}")

    # Very long running time
    for p in comp:
        parts = p['time'].split(':')
        hours = int(parts[0]) if parts else 0
        if hours > 168:  # > 1 week
            warns.append(f"PID {p['pid']} running >{hours}h — verify it's not hung")

    # Zombie parent check — list processes with many children (likely zombie generators)
    if zomb and comp:
        warns.append(f"Zombies present with active compute — parent process may not be reaping")
        warns.append("Run: ssh <host> 'ps -o ppid= -p <zombie_pid>' to identify parent")

    return issues, warns


# ── Connection methods ──────────────────────────────────────────────────────

def connect_paramiko(host, port, user, password, key_file, timeout=30):
    """Run ps aux via paramiko."""
    try:
        import paramiko
    except ImportError:
        raise RuntimeError("paramiko not installed. Run: pip install paramiko")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    kwargs = {'hostname': host, 'port': port, 'username': user,
              'timeout': timeout, 'banner_timeout': timeout}
    if key_file:
        kwargs['key_filename'] = key_file
    elif password:
        kwargs['password'] = password
    # else: rely on default SSH agent / ~/.ssh keys

    try:
        client.connect(**kwargs)
    except Exception as e:
        client.close()
        raise RuntimeError(f"SSH connect failed: {e}")

    stdin, stdout, stderr = client.exec_command('ps aux', timeout=timeout)
    output = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    client.close()

    if err.strip():
        print(f"[remote_ps] stderr: {err.strip()}", file=sys.stderr)

    return output


def connect_native_ssh(host, port, user, key_file, timeout=30):
    """Run ps aux via system ssh command."""
    cmd = ['ssh']
    if key_file:
        cmd.extend(['-i', key_file])
    if port and port != 22:
        cmd.extend(['-p', str(port)])
    cmd.extend([
        '-o', f'ConnectTimeout={timeout}',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'BatchMode=yes',
    ])
    dest = f"{user}@{host}" if user else host
    cmd.append(dest)
    cmd.append('ps aux')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"SSH timed out after {timeout}s — server may be overloaded")
    if result.returncode != 0:
        raise RuntimeError(f"SSH exit {result.returncode}: {result.stderr.strip()}")

    return result.stdout


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description='Remote Linux process inspector')
    p.add_argument('--host', required=True, help='Remote hostname or IP')
    p.add_argument('--port', type=int, default=22, help='SSH port (default 22)')
    p.add_argument('--user', help='SSH username (default: current user)')
    p.add_argument('--password', help='SSH password (paramiko only)')
    p.add_argument('--key-file', help='SSH private key path')
    p.add_argument('--json', action='store_true', help='Output structured JSON')
    p.add_argument('--diagnose', action='store_true', help='Report + flagged issues')
    p.add_argument('--method', choices=['paramiko', 'ssh'], default='paramiko',
                   help='Connection method (default: paramiko)')
    p.add_argument('--timeout', type=int, default=30,
                   help='SSH connect timeout in seconds (default: 30)')
    args = p.parse_args()

    if not args.user:
        args.user = os.environ.get('USER', os.environ.get('USERNAME', 'root'))

    # Connect and fetch
    try:
        if args.method == 'paramiko':
            raw = connect_paramiko(args.host, args.port, args.user,
                                   args.password, args.key_file, args.timeout)
        else:
            raw = connect_native_ssh(args.host, args.port, args.user,
                                     args.key_file, args.timeout)
    except RuntimeError as e:
        result = {'error': str(e), 'host': args.host, 'port': args.port}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"\n  ERROR: {e}")
            print(f"  Suggestions:")
            print(f"    - Try longer timeout: --timeout 60")
            print(f"    - Try a different port if the server has multiple instances")
            print(f"    - Server load may be maxed out (see SSH connection rules)")
        sys.exit(1)

    parsed = parse_ps(raw)
    parsed['host'] = args.host
    parsed['port'] = args.port
    parsed['user'] = args.user

    if args.json:
        # Make JSON-safe
        out = {
            'host': parsed['host'],
            'port': parsed['port'],
            'user': parsed['user'],
            'total': parsed['total'],
            'computing': [{'pid': p['pid'], 'cpu': p['cpu'], 'mem': p['mem'],
                           'time': p['time'], 'cmd': p['cmd'],
                           'label': p.get('_label', '?')} for p in parsed['computing']],
            'zombie': [{'pid': p['pid'], 'stat': p['stat'], 'cmd': p['cmd']}
                       for p in parsed['zombie']],
            'high_load': [{'pid': p['pid'], 'cpu': p['cpu'], 'mem': p['mem'],
                           'cmd': p['cmd']} for p in parsed['high_load']],
            'other_groups': {k: len(v) for k, v in parsed['other_groups'].items()},
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.diagnose:
        issues, warns = diagnose(parsed)
        print(format_report(parsed, args.host, args.user, args.port))
        print()
        if issues:
            print(f"\033[1;31m  ISSUES:\033[0m")
            for i in issues:
                print(f"    ! {i}")
        if warns:
            print(f"\033[1;33m  WARNINGS:\033[0m")
            for w in warns:
                print(f"    ~ {w}")
        if not issues and not warns:
            print(f"\033[1;32m  No issues detected.\033[0m")
    else:
        print(format_report(parsed, args.host, args.user, args.port))


if __name__ == '__main__':
    main()
