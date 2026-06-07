import shutil
from core.jailbreak import safe_exec


def _run(cmd, timeout=8):
    try:
        r = safe_exec(cmd, timeout=timeout)
        return r["stdout"].strip().split("\n")[0][:120] or "no data"
    except Exception as e:
        return str(e)


def _vmstat_mem():
    """Parse vm_stat output into human-readable memory info."""
    try:
        r = safe_exec("vm_stat", timeout=8)
        if not r["success"]:
            return "mem n/a"
        pages = {}
        for line in r["stdout"].strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                val = val.strip().rstrip(".")
                try:
                    pages[key.strip()] = int(val)
                except ValueError:
                    pass
        active = pages.get("Pages active", 0) * 16384
        wired = pages.get("Pages wired down", 0) * 16384
        compressed = pages.get("Pages stored in compressor", 0) * 16384
        free = pages.get("Pages free", 0) * 16384
        total_mb = (active + wired + compressed + free) // 1048576
        used_mb = (active + wired + compressed) // 1048576
        return f"{used_mb}M used / {total_mb}M total"
    except Exception:
        return "mem n/a"


def sys_info(args=""):
    lines = ["[SYS] System Information:"]

    cmds = [
        ("OS", "uname -a"),
        ("Host", "hostname"),
        ("Uptime", "uptime" if shutil.which("uptime") else None),
        ("Memory", None),
        ("Disk", "df -h /"),
        ("CPU cores", "sysctl -n hw.ncpu"),
        ("Load", "sysctl -n vm.loadavg"),
    ]

    for label, cmd in cmds:
        if cmd is None:
            if label == "Memory":
                lines.append(f"  {label}: {_vmstat_mem()}")
            else:
                lines.append(f"  {label}: not available")
            continue
        lines.append(f"  {label}: {_run(cmd)}")

    return "\n".join(lines)


def disk_usage(args=""):
    path = args.strip() or "/"
    out = _run(f"df -h {path}")
    lines = out.split("\n")
    return lines[-1] if len(lines) > 1 else out


def wifi_status(args=""):
    out = _run("ifconfig en0")
    if "no data" in out or "error" in out:
        out = _run("ifconfig lo0")
    return out[:300] if len(out) > 300 else out


SKILL = {
    "name": "system_tools",
    "description": "System info: CPU, memory, disk, uptime, WiFi",
    "run": sys_info,
}
