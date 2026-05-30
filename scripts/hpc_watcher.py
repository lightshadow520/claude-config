#!/usr/bin/env python3
"""
HPC Job Watcher — server-side process guardian for computational chemistry.
Upload this once per server, then invoke for each calculation.

Self-contained: Python 3.6+ stdlib only. No pip dependencies.
Monitors output files, detects deadlocks/OOM/segfaults, writes structured status.

Commands:
  submit  Launch a calculation with full monitoring
  status  Print current job status as JSON
  kill    Stop a job and clean up its process tree
  list    List all managed jobs on this server
  cleanup Remove stale job records

Usage (on server):
  python3 hpc_watcher.py submit --cmd "mpirun -np 32 vasp_std" \\
      --job-dir /home/user/calc/Ni-111 --output "OUTCAR OSZICAR" \\
      --heartbeat 900 --walltime 86400 --code vasp

The watcher writes .hpc_status.json in the job directory.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta

# Cross-platform signal constants (Windows doesn't have SIGKILL/SIGTERM)
SIGTERM = getattr(signal, 'SIGTERM', 15)
SIGKILL = getattr(signal, 'SIGKILL', 9)

JOBS_ROOT = os.path.expanduser("~/.hpc_jobs")
STATUS_FILE = ".hpc_status.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Environment presets per code
# ═══════════════════════════════════════════════════════════════════════════════

ENV_PRESETS = {
    "vasp": {
        "OMP_NUM_THREADS": "1",
        "I_MPI_SHM_LMT": "shm",
        "ulimit_stack": "unlimited",
        "ulimit_core": "0",
    },
    "cp2k": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
    },
    "lammps": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
    },
    "gaussian": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
        "GAUSS_SCRDIR": "/tmp",
    },
    "orca": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
    },
    "qe": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
    },
    "gromacs": {
        "OMP_NUM_THREADS": "1",
        "ulimit_stack": "unlimited",
    },
}


def apply_env(code):
    """Apply environment presets for the given code."""
    preset = ENV_PRESETS.get(code, ENV_PRESETS.get("vasp", {}))
    for key, val in preset.items():
        if key.startswith("ulimit_"):
            continue  # handled separately
        os.environ[key] = val
    # ulimits
    if "ulimit_stack" in preset:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        except Exception:
            pass
    if "ulimit_core" in preset:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def now_iso():
    return datetime.now().isoformat()


def get_dir_mtime(dirpath):
    """Get the latest mtime of any regular file within dirpath (recursive, depth 3)."""
    latest = 0
    try:
        for root, dirs, files in os.walk(dirpath):
            depth = root[len(dirpath):].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            for f in files:
                fp = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(fp)
                    if mtime > latest:
                        latest = mtime
                except OSError:
                    pass
    except Exception:
        pass
    return latest


def get_process_rss_mb(pid):
    """Read RSS from /proc/<pid>/status. Returns MB."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def check_dmesg_oom(since_ts, code_hint="vasp"):
    """Check dmesg for OOM kills since a timestamp."""
    try:
        out = subprocess.run(
            ["dmesg", "-T"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        # dmesg not accessible — try /var/log
        try:
            for logfile in ["/var/log/syslog", "/var/log/messages", "/var/log/kern.log"]:
                if os.path.exists(logfile):
                    out = subprocess.run(
                        ["grep", "-i", r"out of memory|oom.kill", logfile],
                        capture_output=True, text=True, timeout=10
                    )
                    break
            else:
                return {"detected": False, "note": "dmesg/syslog not accessible"}
        except Exception:
            return {"detected": False, "note": "dmesg/syslog not accessible"}

    if out.returncode != 0:
        return {"detected": False}

    # Filter for recent entries containing our code name
    lines = out.stdout.strip().split('\n') if out.stdout.strip() else []
    recent = []
    for line in lines:
        if code_hint.lower() in line.lower() or "killed process" in line.lower():
            recent.append(line.strip()[-200:])

    return {
        "detected": len(recent) > 0,
        "lines": recent[-5:],
    }


def kill_process_tree(pid, sig=SIGKILL):
    """Kill a process and all its children."""
    try:
        # Get child PIDs
        children = subprocess.run(
            ["ps", "--ppid", str(pid), "-o", "pid="],
            capture_output=True, text=True, timeout=5
        )
        for child_pid in children.stdout.strip().split():
            try:
                kill_process_tree(int(child_pid), sig)
            except Exception:
                pass
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except Exception:
        pass


def write_status(job_dir, data):
    """Atomically write status file."""
    path = os.path.join(job_dir, STATUS_FILE)
    tmp = path + ".tmp"
    data["updated_at"] = now_iso()
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def read_status(job_dir):
    """Read status file, return None if missing."""
    path = os.path.join(job_dir, STATUS_FILE)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostics: classify non-zero exit
# ═══════════════════════════════════════════════════════════════════════════════

def diagnose_exit(job_dir, exit_code, code, start_time):
    """Figure out why a calculation exited non-zero."""
    result = {
        "exit_code": exit_code,
        "error_type": "unknown",
        "suggestion": None,
        "dmesg_oom": None,
    }

    # Check dmesg for OOM
    dmesg = check_dmesg_oom(start_time, code)
    result["dmesg_oom"] = dmesg

    if exit_code == -9 or exit_code == 137:
        result["error_type"] = "killed_by_signal"
        result["signal"] = "SIGKILL"
        if dmesg["detected"]:
            result["error_type"] = "oom_killed"
            result["suggestion"] = (
                f"Memory exhausted. Reduce problem size, lower ENCUT/cutoff, "
                f"or use fewer MPI ranks per node. Check if other jobs are consuming memory."
            )

    elif exit_code == -11 or exit_code == 139:
        result["error_type"] = "segfault"
        result["signal"] = "SIGSEGV"
        result["suggestion"] = (
            "Segmentation fault. Set ulimit -s unlimited. "
            "Check stack size (try OMP_STACKSIZE=512M). "
            "Reduce memory per core (NCORE for VASP, OMP_NUM_THREADS for others). "
            "Check input file geometry for overlapping atoms."
        )

    elif exit_code == -6 or exit_code == 134:
        result["error_type"] = "aborted"
        result["signal"] = "SIGABRT"
        result["suggestion"] = (
            "Process aborted (SIGABRT). Usually an assertion failure in the code. "
            "Check input file syntax, especially INCAR/POSCAR tags for VASP."
        )

    elif exit_code == -15 or exit_code == 143:
        result["error_type"] = "terminated"
        result["signal"] = "SIGTERM"
        result["suggestion"] = "Process was terminated (SIGTERM). May have hit a queue walltime limit."

    elif exit_code == 1:
        result["error_type"] = "generic_error"
        result["suggestion"] = (
            "Generic exit code 1. Check output file for specific error messages. "
            "Common causes: bad input parameters, missing files, MPI launch failure."
        )

    # Tail last 20 lines of output files for clues
    clues = []
    for fname in ["OUTCAR", "OSZICAR", "log.lammps", "cp2k.out", "*.log", "*.out"]:
        patterns = [fname] if '*' not in fname else []
        if '*' in fname:
            import glob
            patterns = glob.glob(os.path.join(job_dir, fname))
        for pat in patterns:
            fpath = os.path.join(job_dir, pat) if not os.path.isabs(pat) else pat
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'rb') as f:
                        f.seek(max(0, os.path.getsize(fpath) - 4096))
                        tail = f.read().decode('utf-8', errors='replace')
                    clues.append({"file": os.path.basename(fpath), "tail": tail[-500:]})
                except Exception:
                    pass

    if clues:
        result["output_tails"] = clues

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Submit: launch + monitor
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_submit(args):
    job_dir = os.path.abspath(args.job_dir)
    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(JOBS_ROOT, exist_ok=True)

    # Check existing job
    existing = read_status(job_dir)
    if existing and existing.get("status") == "running":
        pid = existing.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                print(json.dumps({"error": f"Job already running in {job_dir} (PID {pid})"}))
                sys.exit(1)
            except OSError:
                pass  # stale PID

    # Apply environment
    apply_env(args.code)

    # Build command
    cmd = args.cmd
    if not cmd:
        print(json.dumps({"error": "--cmd is required"}))
        sys.exit(1)

    start_time = datetime.now()
    start_ts = start_time.isoformat()

    # Launch
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=job_dir,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as e:
        result = {
            "status": "launch_failed",
            "error": str(e),
            "started_at": start_ts,
        }
        write_status(job_dir, result)
        print(json.dumps(result))
        sys.exit(1)

    pid = proc.pid
    heartbeat = args.heartbeat
    walltime = args.walltime
    output_files = [f.strip() for f in args.output.split()] if args.output else []

    # Write initial status
    initial = {
        "job_id": f"{os.path.basename(job_dir)}_{pid}_{int(time.time())}",
        "status": "running",
        "pid": pid,
        "code": args.code,
        "command": cmd,
        "job_dir": job_dir,
        "started_at": start_ts,
        "heartbeat": heartbeat,
        "walltime": walltime,
        "last_activity": start_ts,
        "output_size": 0,
        "max_rss_mb": 0.0,
        "dmesg_oom": None,
        "error": None,
        "suggestion": None,
    }
    write_status(job_dir, initial)

    # Symlink to JOBS_ROOT for list command
    job_link = os.path.join(JOBS_ROOT, os.path.basename(job_dir))
    if not os.path.exists(job_link):
        try:
            os.symlink(job_dir, job_link)
        except OSError:
            pass

    # ── Monitor loop ────────────────────────────────────────────────────
    last_mtime = get_dir_mtime(job_dir) or time.time()
    last_activity_time = time.time()
    peak_rss = 0.0
    check_interval = max(heartbeat / 5, 15)  # check 5x per heartbeat window, min 15s

    try:
        while True:
            time.sleep(check_interval)

            # Check process
            ret = proc.poll()
            elapsed = (datetime.now() - start_time).total_seconds()

            if ret is not None:
                # Process exited
                final_status = "completed" if ret == 0 else "failed"
                diag = None
                if ret != 0:
                    diag = diagnose_exit(job_dir, ret, args.code, start_ts)
                result = {
                    "status": final_status,
                    "exit_code": ret,
                    "elapsed_sec": elapsed,
                    "max_rss_mb": peak_rss,
                    "finished_at": now_iso(),
                }
                if diag:
                    result.update(diag)
                write_status(job_dir, {**initial, **result})
                print(json.dumps(result))
                return

            # Check walltime
            if elapsed > walltime:
                kill_process_tree(pid, SIGTERM)
                time.sleep(5)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    kill_process_tree(pid, SIGKILL)
                result = {
                    "status": "timeout",
                    "elapsed_sec": elapsed,
                    "max_rss_mb": peak_rss,
                    "suggestion": f"Walltime {walltime}s exceeded. Increase walltime or reduce system size.",
                    "finished_at": now_iso(),
                }
                write_status(job_dir, {**initial, **result})
                print(json.dumps(result))
                return

            # Track RSS
            rss = get_process_rss_mb(pid)
            if rss > peak_rss:
                peak_rss = rss

            # Check directory activity
            current_mtime = get_dir_mtime(job_dir)
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                last_activity_time = time.time()
            else:
                idle_sec = time.time() - last_activity_time
                if idle_sec > heartbeat:
                    # DEADLOCK detected
                    kill_process_tree(pid, SIGKILL)
                    result = {
                        "status": "deadlock",
                        "elapsed_sec": elapsed,
                        "max_rss_mb": peak_rss,
                        "error_type": "Deadlock_Timeout",
                        "idle_sec": idle_sec,
                        "suggestion": (
                            f"No file activity for {idle_sec:.0f}s in {job_dir}. "
                            "Calculation is stalled/deadlocked. "
                            "Common causes: MPI hang, I/O deadlock, infinite SCF loop, "
                            "bad geometry causing FFT blowup."
                        ),
                        "finished_at": now_iso(),
                    }
                    write_status(job_dir, {**initial, **result})
                    print(json.dumps(result))
                    return

            # Periodic status update
            write_status(job_dir, {
                **initial,
                "elapsed_sec": elapsed,
                "last_activity_ago": time.time() - last_activity_time,
                "max_rss_mb": peak_rss,
            })

    except KeyboardInterrupt:
        # Watcher itself being killed — clean up
        kill_process_tree(pid, SIGKILL)
        result = {"status": "killed", "finished_at": now_iso()}
        write_status(job_dir, {**initial, **result})
        print(json.dumps(result))


# ═══════════════════════════════════════════════════════════════════════════════
# Status: read and print
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_status(args):
    job_dir = os.path.abspath(args.job_dir)
    status = read_status(job_dir)
    if status is None:
        print(json.dumps({"status": "not_found", "job_dir": job_dir}))
        return

    # If running, check watcher is actually alive
    if status.get("status") == "running":
        pid = status.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                status["status"] = "lost"
                status["note"] = f"Process PID {pid} no longer exists — server may have rebooted or process was killed externally"
                status["finished_at"] = now_iso()
                write_status(job_dir, status)

    print(json.dumps(status, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# Kill
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_kill(args):
    job_dir = os.path.abspath(args.job_dir)
    status = read_status(job_dir)
    if status is None:
        print(json.dumps({"status": "not_found", "job_dir": job_dir}))
        return

    pid = status.get("pid")
    killed = False
    if pid and status.get("status") == "running":
        try:
            kill_process_tree(pid, SIGTERM)
            time.sleep(3)
            try:
                os.kill(pid, 0)
                kill_process_tree(pid, SIGKILL)
            except OSError:
                pass
            killed = True
        except Exception as e:
            print(json.dumps({"status": "kill_failed", "error": str(e)}))
            return

    status["status"] = "killed"
    status["finished_at"] = now_iso()
    write_status(job_dir, status)
    print(json.dumps({"status": "killed", "pid": pid, "killed": killed}))


# ═══════════════════════════════════════════════════════════════════════════════
# List
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_list(args):
    results = []
    if os.path.isdir(JOBS_ROOT):
        for entry in os.listdir(JOBS_ROOT):
            link = os.path.join(JOBS_ROOT, entry)
            target = None
            try:
                target = os.readlink(link)
            except OSError:
                pass
            if target:
                status = read_status(target)
            else:
                status = read_status(link)
            if status:
                results.append({
                    "name": os.path.basename(target or entry),
                    "job_dir": target or entry,
                    "status": status.get("status", "?"),
                    "code": status.get("code", "?"),
                    "started_at": status.get("started_at", "?"),
                    "elapsed_sec": status.get("elapsed_sec", 0),
                    "max_rss_mb": status.get("max_rss_mb", 0),
                })

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No managed jobs found.")
            return
        print(f"{'JOB':<30} {'STATUS':<12} {'CODE':<8} {'ELAPSED':<10} {'RSS(MB)':<10}")
        print("-" * 70)
        for r in sorted(results, key=lambda x: x.get("started_at", ""), reverse=True):
            elapsed = r.get("elapsed_sec", 0)
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            print(f"{r['name']:<30} {r['status']:<12} {r['code']:<8} "
                  f"{h}h{m:02d}m{'':<4} {r.get('max_rss_mb', 0):<10.0f}")


# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_cleanup(args):
    if os.path.isdir(JOBS_ROOT):
        for entry in os.listdir(JOBS_ROOT):
            link = os.path.join(JOBS_ROOT, entry)
            target = None
            try:
                target = os.readlink(link)
            except OSError:
                try:
                    os.remove(link)
                except OSError:
                    pass
                continue
            status = read_status(target) if target else None
            if status and status.get("status") in ("completed", "failed", "killed", "lost", "not_found"):
                try:
                    os.remove(link)
                    print(f"Cleaned: {entry}")
                except OSError:
                    pass
    print("Cleanup done.")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="HPC Job Watcher — server-side process guardian")
    sp = p.add_subparsers(dest="command")

    # submit
    s_sub = sp.add_parser("submit", help="Launch a calculation with monitoring")
    s_sub.add_argument("--cmd", required=True, help="Shell command to run")
    s_sub.add_argument("--job-dir", required=True, help="Working directory")
    s_sub.add_argument("--output", default="OUTCAR", help="Output files to track (space-separated)")
    s_sub.add_argument("--code", default="vasp", help="Code name (vasp/cp2k/lammps/gaussian/orca/qe/gromacs)")
    s_sub.add_argument("--heartbeat", type=int, default=900,
                       help="Max idle seconds before deadlock kill (default: 900 = 15 min)")
    s_sub.add_argument("--walltime", type=int, default=86400,
                       help="Max walltime seconds (default: 86400 = 24h)")

    # status
    st_sub = sp.add_parser("status", help="Check job status")
    st_sub.add_argument("--job-dir", required=True, help="Working directory")

    # kill
    k_sub = sp.add_parser("kill", help="Stop a job")
    k_sub.add_argument("--job-dir", required=True, help="Working directory")

    # list
    sp.add_parser("list", help="List all managed jobs")

    # cleanup
    sp.add_parser("cleanup", help="Remove stale job records")

    args = p.parse_args()

    if args.command == "submit":
        cmd_submit(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "kill":
        cmd_kill(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
