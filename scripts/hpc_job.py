#!/usr/bin/env python3
"""
HPC Job Controller — local tool for managing remote HPC calculations.
This is the AI agent's interface. Never SSH directly; always go through this.

Commands:
  upload   Copy hpc_watcher.py to remote server
  submit   Launch a calculation on remote server
  check    Get job status + auto-diagnose failures
  kill     Stop a job (requires user approval!)
  list     List all jobs on a server
  logs     Download and show recent output

Usage:
  python scripts/hpc_job.py upload   --host node01 --port 22
  python scripts/hpc_job.py submit   --host node01 --code vasp --dir /home/user/calc/Ni-111 \\
                                     --cmd "mpirun -np 32 vasp_std" --cores 32
  python scripts/hpc_job.py check    --host node01 --dir /home/user/calc/Ni-111 [--diagnose]
  python scripts/hpc_job.py kill     --host node01 --dir /home/user/calc/Ni-111
  python scripts/hpc_job.py list     --host node01
  python scripts/hpc_job.py logs     --host node01 --dir /home/user/calc/Ni-111 --tail 50
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHER_PATH = os.path.join(SCRIPT_DIR, "hpc_watcher.py")
CHECK_CALC_PATH = os.path.join(SCRIPT_DIR, "check_calc.py")
REMOTE_WATCHER = "~/hpc_watcher.py"


# ═══════════════════════════════════════════════════════════════════════════════
# SSH helpers
# ═══════════════════════════════════════════════════════════════════════════════

def ssh_cmd(host, port, user=None, key_file=None, timeout=30):
    """Build SSH command prefix."""
    cmd = ["ssh"]
    if key_file:
        cmd.extend(["-i", key_file])
    if port and port != 22:
        cmd.extend(["-p", str(port)])
    cmd.extend([
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
    ])
    dest = f"{user}@{host}" if user else host
    cmd.append(dest)
    return cmd


def ssh_run(host, port, remote_cmd, user=None, key_file=None, timeout=30, capture=True):
    """Run a command on remote server via SSH. Returns (returncode, stdout, stderr)."""
    cmd = ssh_cmd(host, port, user, key_file, timeout) + [remote_cmd]
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout + 10)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"SSH timed out after {timeout}s"


def scp_upload(local_path, remote_path, host, port, user=None, key_file=None, timeout=30):
    """Upload a file to remote server."""
    dest = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
    cmd = ["scp"]
    if key_file:
        cmd.extend(["-i", key_file])
    if port and port != 22:
        cmd.extend(["-P", str(port)])
    cmd.extend([
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
    ])
    cmd.extend([local_path, dest])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    return result.returncode, result.stdout, result.stderr


def scp_download(remote_path, local_path, host, port, user=None, key_file=None, timeout=30):
    """Download a file from remote server."""
    src = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
    cmd = ["scp"]
    if key_file:
        cmd.extend(["-i", key_file])
    if port and port != 22:
        cmd.extend(["-P", str(port)])
    cmd.extend([
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
    ])
    cmd.extend([src, local_path])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
    return result.returncode, result.stdout, result.stderr


# ═══════════════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_upload(args):
    """Upload hpc_watcher.py to remote server."""
    print(f"Uploading hpc_watcher.py to {args.host}...")
    ret, out, err = scp_upload(
        WATCHER_PATH, REMOTE_WATCHER,
        args.host, args.port, args.user, args.key_file, args.timeout
    )
    if ret != 0:
        print(f"ERROR: Upload failed: {err}")
        sys.exit(1)
    # Verify python3 is available and script runs
    ret, out, err = ssh_run(
        args.host, args.port, f"python3 {REMOTE_WATCHER} --help",
        args.user, args.key_file, args.timeout
    )
    if ret != 0:
        print(f"WARNING: Watcher uploaded but may not run: {err}")
        print(f"  Try: ssh {args.host} 'python3 ~/hpc_watcher.py --help'")
    else:
        print(f"OK: hpc_watcher.py ready on {args.host}")


def cmd_submit(args):
    """Submit a calculation to remote server."""
    # 1. Check watcher exists
    ret, _, err = ssh_run(
        args.host, args.port, f"test -f {REMOTE_WATCHER} && echo OK || echo MISSING",
        args.user, args.key_file, args.timeout
    )
    if "MISSING" in (_ or ""):
        print("Watcher not found on server. Run 'upload' first.")
        print(f"  python {__file__} upload --host {args.host}")
        sys.exit(1)

    # 2. Build submit command
    output = args.output or get_default_output(args.code)
    watcher_cmd = (
        f"python3 {REMOTE_WATCHER} submit "
        f"--cmd '{args.cmd}' "
        f"--job-dir '{args.dir}' "
        f"--code {args.code} "
        f"--output '{output}' "
        f"--heartbeat {args.heartbeat} "
        f"--walltime {args.walltime}"
    )

    # 3. Launch via nohup
    remote_cmd = f"nohup {watcher_cmd} > /dev/null 2>&1 & sleep 2 && python3 {REMOTE_WATCHER} status --job-dir '{args.dir}'"

    print(f"Submitting {args.code} job to {args.host}:{args.dir} ...")
    ret, out, err = ssh_run(
        args.host, args.port, remote_cmd,
        args.user, args.key_file, args.timeout
    )

    if ret != 0:
        print(f"ERROR: {err}")
        sys.exit(1)

    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse status. Raw output:\n{out}")
        sys.exit(1)

    print_submit_result(status, args)


def print_submit_result(status, args):
    """Pretty-print submit result for AI consumption."""
    print()
    print(f"  {'─'*56}")
    if "error" in status:
        print(f"  SUBMIT ERROR: {status['error']}")
        return

    s = status.get("status", "?")
    icon = {"running": "🟢", "completed": "✅", "failed": "🔴"}.get(s, "⚪")
    print(f"  {icon} Job Status: {s}")
    print(f"  Job ID:      {status.get('job_id', '?')}")
    print(f"  Directory:   {status.get('job_dir', args.dir)}")
    print(f"  PID:         {status.get('pid', '?')}")
    print(f"  Code:        {status.get('code', args.code)}")
    print(f"  Started:     {status.get('started_at', '?')}")
    if status.get("status") == "failed":
        print(f"  Error Type:  {status.get('error_type', '?')}")
        if status.get("suggestion"):
            print(f"  Suggestion:  {status['suggestion']}")
    print(f"  {'─'*56}")
    print()
    print(f"  Check status later:")
    print(f"  python {__file__} check --host {args.host} --dir '{args.dir}' --diagnose")


def cmd_check(args):
    """Check job status on remote server."""
    remote_cmd = f"python3 {REMOTE_WATCHER} status --job-dir '{args.dir}'"
    ret, out, err = ssh_run(
        args.host, args.port, remote_cmd,
        args.user, args.key_file, args.timeout
    )

    if ret != 0:
        print(f"ERROR: {err}")
        sys.exit(1)

    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse status. Raw:\n{out}")
        sys.exit(1)

    print_status(status, args)

    # Auto-diagnose on failure
    if args.diagnose and status.get("status") in ("failed", "deadlock", "oom_killed", "timeout"):
        print()
        print(f"  {'─'*56}")
        print(f"  Running diagnostics...")
        run_diagnostics(args, status)


def print_status(status, args):
    """Pretty-print job status."""
    s = status.get("status", "?")
    icons = {
        "running": "🟢", "completed": "✅", "failed": "🔴",
        "deadlock": "💀", "oom_killed": "💥", "timeout": "⏰",
        "killed": "🛑", "lost": "❓", "not_found": "⚪",
    }
    icon = icons.get(s, "⚪")

    print()
    print(f"  {'─'*56}")
    print(f"  {icon} Status:     {s}")
    print(f"  Directory:   {status.get('job_dir', args.dir)}")
    print(f"  PID:         {status.get('pid', '?')}")
    print(f"  Code:        {status.get('code', '?')}")
    print(f"  Started:     {status.get('started_at', '?')}")
    elapsed = status.get("elapsed_sec", 0)
    if elapsed:
        h, m = int(elapsed // 3600), int((elapsed % 3600) // 60)
        print(f"  Elapsed:     {h}h {m:02d}m")
    print(f"  Max RSS:     {status.get('max_rss_mb', 0):.0f} MB")
    if status.get("last_activity_ago"):
        print(f"  Last active: {status['last_activity_ago']:.0f}s ago")

    if s == "failed":
        print(f"  Exit code:   {status.get('exit_code', '?')}")
        print(f"  Error type:  {status.get('error_type', '?')}")
        if status.get("suggestion"):
            print(f"  Suggestion:  {status['suggestion']}")

    if s == "deadlock":
        print(f"  Idle for:    {status.get('idle_sec', 0):.0f}s")
        print(f"  Error type:  {status.get('error_type', '?')}")
        if status.get("suggestion"):
            print(f"  Suggestion:  {status['suggestion']}")

    print(f"  {'─'*56}")
    print()


def run_diagnostics(args, status):
    """Download output files and run check_calc.py for deep analysis."""
    code = status.get("code", args.code)
    job_dir = status.get("job_dir", args.dir)

    # Determine output file to download
    output_map = {
        "vasp": "OUTCAR",
        "cp2k": None,  # will glob *.out
        "lammps": "log.lammps",
        "gaussian": None,  # will glob *.log
        "orca": None,
        "qe": None,
        "gromacs": None,
    }
    output_file = output_map.get(code, "OUTCAR")

    tmpdir = tempfile.mkdtemp(prefix="hpc_diag_")
    local_path = None

    if output_file:
        remote_path = f"{job_dir}/{output_file}"
        local_path = os.path.join(tmpdir, output_file)
        print(f"  Downloading {remote_path} ...")
        ret, _, err = scp_download(
            remote_path, local_path,
            args.host, args.port, args.user, args.key_file, args.timeout
        )
        if ret != 0:
            print(f"  WARNING: Could not download output: {err}")
        else:
            print(f"  Downloaded to {local_path}")

    if local_path and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        print()
        print(f"  Running check_calc.py --diagnose ...")
        check_script = CHECK_CALC_PATH
        if os.path.exists(check_script):
            result = subprocess.run(
                ["python", check_script, local_path, "--diagnose"],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        else:
            print(f"  check_calc.py not found at {check_script}")

    # Cleanup temp
    try:
        import shutil
        shutil.rmtree(tmpdir)
    except Exception:
        pass


def cmd_kill(args):
    """Kill a remote job. REQUIRES USER APPROVAL before calling."""
    # First get status
    remote_cmd = f"python3 {REMOTE_WATCHER} status --job-dir '{args.dir}'"
    ret, out, err = ssh_run(
        args.host, args.port, remote_cmd,
        args.user, args.key_file, args.timeout
    )

    status = {}
    try:
        status = json.loads(out) if out else {}
    except json.JSONDecodeError:
        pass

    if status.get("status") != "running":
        print(f"Job is not running (status: {status.get('status', 'unknown')})")
        if not args.force:
            print("Nothing to kill. Use --force to clear stale status.")
            return

    # Print what we're about to kill
    print()
    print(f"  ⚠ ABOUT TO KILL:")
    print(f"  Host:    {args.host}")
    print(f"  Dir:     {args.dir}")
    print(f"  PID:     {status.get('pid', '?')}")
    print(f"  Code:    {status.get('code', '?')}")
    print(f"  Elapsed: {status.get('elapsed_sec', 0):.0f}s")
    print()
    print(f"  This will kill the calculation process tree.")
    print(f"  Output files in {args.dir} will be preserved.")

    if not args.confirm:
        print()
        print(f"  ⛔ USER APPROVAL REQUIRED. Re-run with --confirm to proceed.")
        print(f"     Review the above information before confirming.")
        sys.exit(0)

    # Execute kill
    remote_cmd = f"python3 {REMOTE_WATCHER} kill --job-dir '{args.dir}'"
    ret, out, err = ssh_run(
        args.host, args.port, remote_cmd,
        args.user, args.key_file, args.timeout
    )

    try:
        result = json.loads(out) if out else {}
    except json.JSONDecodeError:
        print(f"Kill result: {out}")
        return

    if result.get("killed"):
        print(f"  Job killed. PID {result.get('pid')} terminated.")
    else:
        print(f"  Kill result: {result}")


def cmd_list(args):
    """List all managed jobs on remote server."""
    ret, out, err = ssh_run(
        args.host, args.port, f"python3 {REMOTE_WATCHER} list --json",
        args.user, args.key_file, args.timeout
    )

    if ret != 0:
        print(f"ERROR: {err}")
        sys.exit(1)

    try:
        jobs = json.loads(out)
    except json.JSONDecodeError:
        print(f"No jobs found.")
        return

    if not jobs:
        print("No managed jobs on this server.")
        return

    print()
    print(f"  Jobs on {args.host}:")
    print(f"  {'JOB':<24} {'STATUS':<12} {'CODE':<8} {'ELAPSED':<10} {'RSS':<8}")
    print(f"  {'-'*24} {'-'*12} {'-'*8} {'-'*10} {'-'*8}")
    for j in sorted(jobs, key=lambda x: x.get("started_at", ""), reverse=True):
        name = j.get("name", "?")[:24]
        s = j.get("status", "?")
        code = j.get("code", "?")
        elapsed = j.get("elapsed_sec", 0)
        h, m = int(elapsed // 3600), int((elapsed % 3600) // 60)
        rss = j.get("max_rss_mb", 0)
        print(f"  {name:<24} {s:<12} {code:<8} {h}h{m:02d}m{'':<3} {rss:<8.0f}")
    print()


def cmd_logs(args):
    """Download and show recent output from a running job."""
    job_dir = args.dir
    tail_lines = args.tail

    # First check status to find output file
    ret, out, _ = ssh_run(
        args.host, args.port, f"python3 {REMOTE_WATCHER} status --job-dir '{job_dir}'",
        args.user, args.key_file, args.timeout
    )
    try:
        status = json.loads(out) if out else {}
    except json.JSONDecodeError:
        status = {}

    code = status.get("code", args.code or "vasp")
    output_file = get_output_file(code, job_dir, args)

    if not output_file:
        # Try common names
        for fname in ["OUTCAR", "OSZICAR", "log.lammps", "cp2k.out"]:
            ret, test_out, _ = ssh_run(
                args.host, args.port, f"test -f '{job_dir}/{fname}' && echo OK || echo NO",
                args.user, args.key_file, args.timeout
            )
            if "OK" in (test_out or ""):
                output_file = fname
                break
        if not output_file:
            output_file = args.output or "OUTCAR"

    remote_path = f"{job_dir}/{output_file}"
    ret, out, err = ssh_run(
        args.host, args.port,
        f"tail -n {tail_lines} '{remote_path}' 2>/dev/null || echo '[file not found or empty]'",
        args.user, args.key_file, args.timeout
    )

    print()
    print(f"  ── Last {tail_lines} lines of {remote_path} ──")
    print(out or "(empty)")
    print(f"  {'─'*56}")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def get_default_output(code):
    """Return default output file(s) for a code."""
    return {
        "vasp": "OUTCAR OSZICAR",
        "cp2k": "*.out",
        "lammps": "log.lammps",
        "gaussian": "*.log",
        "orca": "*.out",
        "qe": "*.out",
        "gromacs": "*.log",
    }.get(code, "*.out")


def get_output_file(code, job_dir, args):
    """Determine the output file for a code."""
    return {
        "vasp": "OUTCAR",
        "cp2k": None,  # need to glob
        "lammps": "log.lammps",
        "gaussian": None,
        "orca": None,
        "qe": None,
        "gromacs": None,
    }.get(code, "OUTCAR")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="HPC Job Controller — manage remote calculations safely"
    )
    sp = p.add_subparsers(dest="command")

    # ── Upload ──
    up = sp.add_parser("upload", help="Upload hpc_watcher.py to remote server")
    add_conn_args(up)

    # ── Submit ──
    sub = sp.add_parser("submit", help="Launch a calculation")
    add_conn_args(sub)
    sub.add_argument("--code", required=True,
                     help="Code: vasp/cp2k/lammps/gaussian/orca/qe/gromacs")
    sub.add_argument("--dir", required=True,
                     help="Working directory on remote server")
    sub.add_argument("--cmd", required=True,
                     help="Shell command (e.g. 'mpirun -np 32 vasp_std')")
    sub.add_argument("--output", help="Output file(s) to track")
    sub.add_argument("--cores", type=int, default=1, help="Number of cores")
    sub.add_argument("--heartbeat", type=int, default=900,
                     help="Max idle seconds before deadlock kill (default 900)")
    sub.add_argument("--walltime", type=int, default=86400,
                     help="Max walltime seconds (default 86400 = 24h)")

    # ── Check ──
    chk = sp.add_parser("check", help="Check job status")
    add_conn_args(chk)
    chk.add_argument("--dir", required=True, help="Working directory on remote server")
    chk.add_argument("--diagnose", action="store_true", default=True,
                     help="Auto-run diagnostics on failure (default: true)")
    chk.add_argument("--no-diagnose", action="store_false", dest="diagnose",
                     help="Skip diagnostics")

    # ── Kill ──
    kll = sp.add_parser("kill", help="Stop a job (REQUIRES USER APPROVAL)")
    add_conn_args(kll)
    kll.add_argument("--dir", required=True, help="Working directory")
    kll.add_argument("--confirm", action="store_true",
                     help="Confirm you want to kill this job")
    kll.add_argument("--force", action="store_true",
                     help="Force kill even if status is not running")

    # ── List ──
    lst = sp.add_parser("list", help="List all jobs on server")
    add_conn_args(lst)

    # ── Logs ──
    log = sp.add_parser("logs", help="Show recent output from a job")
    add_conn_args(log)
    log.add_argument("--dir", required=True, help="Working directory")
    log.add_argument("--tail", type=int, default=50, help="Number of lines (default 50)")
    log.add_argument("--output", help="Specific output file name")
    log.add_argument("--code", help="Code name to guess output file")

    args = p.parse_args()

    if args.command == "upload":
        cmd_upload(args)
    elif args.command == "submit":
        cmd_submit(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "kill":
        cmd_kill(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "logs":
        cmd_logs(args)
    else:
        p.print_help()
        sys.exit(1)


def add_conn_args(parser):
    """Add SSH connection arguments to a parser."""
    parser.add_argument("--host", required=True, help="Remote hostname or IP")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default 22)")
    parser.add_argument("--user", help="SSH username")
    parser.add_argument("--key-file", help="SSH private key path")
    parser.add_argument("--timeout", type=int, default=30,
                        help="SSH timeout in seconds (default 30)")


if __name__ == "__main__":
    main()
