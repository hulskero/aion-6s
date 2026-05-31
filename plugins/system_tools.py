import subprocess
import os
import shutil


def sys_info(args=""):
    lines = ["[SYS] System Information:"]

    cmds = [
        ("OS", "uname -a"),
        ("Uptime", "uptime" if shutil.which("uptime") else None),
        ("Memory", "free -h 2>/dev/null || echo 'mem n/a'"),
        ("Disk", "df -h / 2>/dev/null | tail -1 || echo 'disk n/a'"),
        ("CPU", "sysctl -n hw.ncpu 2>/dev/null || echo 'cpu n/a'"),
        ("Load", "sysctl -n vm.loadavg 2>/dev/null || echo 'load n/a'"),
        ("Processes", "ps aux 2>/dev/null | wc -l || echo 'ps n/a'"),
    ]

    for label, cmd in cmds:
        if cmd is None:
            lines.append(f"  {label}: not available")
            continue
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            out = r.stdout.strip().split("\n")[0][:120] or "no data"
            lines.append(f"  {label}: {out}")
        except Exception as e:
            lines.append(f"  {label}: {e}")

    return "\n".join(lines)


def disk_usage(args=""):
    path = args.strip() or "/"
    try:
        r = subprocess.run(
            f"du -sh {path} 2>/dev/null || df -h {path} 2>/dev/null | tail -1",
            shell=True, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() or "n/a"
    except Exception as e:
        return f"error: {e}"


def wifi_status(args=""):
    try:
        if os.path.exists("/System/Library/PrivateFrameworks/MobileWiFi.framework"):
            r = subprocess.run(
                ["wlancfg", "show", "en0"],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout.strip()[:300] or "WiFi info unavailable"
        r = subprocess.run(
            "ifconfig en0 2>/dev/null || ifconfig lo0 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip()[:300] or "No WiFi interface found"
    except Exception as e:
        return f"error: {e}"


SKILL = {
    "name": "system_tools",
    "description": "System info: CPU, memory, disk, uptime, WiFi",
    "run": sys_info,
}
