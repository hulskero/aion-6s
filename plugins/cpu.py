#!/usr/bin/env python3
"""CPU status plugin: load average, process count, uptime"""
import subprocess

def run(args=""):
    try:
        up = subprocess.run(["/var/jb/usr/bin/uptime"], capture_output=True, text=True, timeout=5).stdout.strip()
        load_part = up.split("load average:")[-1].strip() if "load average:" in up else "n/a"
        ps = subprocess.run(["ps", "-A"], capture_output=True, text=True, timeout=5).stdout
        proc_count = len(ps.split("\n")) - 1
        uptime_str = up.split("up")[1].split(",")[0].strip() if "up" in up else "n/a"
        return f"Load: {load_part}  |  Processes: {proc_count}  |  Uptime: {uptime_str}"
    except Exception as e:
        return f"CPU error: {e}"

SKILL = {"name": "cpu", "description": "CPU load, process count, uptime", "run": run}
