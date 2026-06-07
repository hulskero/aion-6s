import shutil
import shlex
from core.jailbreak import safe_exec

TOOLS_CHECK = [
    ("apt", "Package manager"),
    ("dpkg", "Debian packager"),
    ("git", "Version control"),
    ("wget", "Download tool"),
    ("rsync", "File sync"),
    ("curl", "HTTP client"),
    ("unzip", "ZIP extract"),
    ("tar", "Tape archive"),
    ("gzip", "GZip compress"),
    ("bzip2", "BZip2 compress"),
    ("ioreg", "IO Registry (IOKitTools)"),
    ("rc", "RemoteCompanion (NFC)"),
    ("shortcuts", "Shortcuts CLI"),
    ("killall", "Kill by name"),
    ("launchctl", "Service manager"),
    ("sysctl", "Kernel parameters"),
    ("ifconfig", "Network config"),
    ("vm_stat", "Memory stats"),
    ("df", "Disk free"),
    ("uptime", "Uptime"),
    ("afplay", "Audio player"),
    ("python3", "Python 3"),
    ("activator", "Activator events"),
]

TOOLS_HELP = """\
Usage:
  @plugin tools check              — scan all tools, show installed/missing
  @plugin tools install <pkg>      — apt install -y <pkg> (requires apt)
  @plugin tools list               — show all known tools
"""


def _check_tools():
    lines = []
    lines.append("CLI Tool Check")
    lines.append(f"{'Tool':<16} {'Status':<10} {'Path'}")
    lines.append("-" * 50)
    available = 0
    for name, desc in TOOLS_CHECK:
        path = shutil.which(name)
        if path:
            lines.append(f"{name:<16} {'✅':<10} {path}")
            available += 1
        else:
            lines.append(f"{name:<16} {'❌':<10} (not installed)")
    lines.append("-" * 50)
    lines.append(f"{available}/{len(TOOLS_CHECK)} tools available")
    return "\n".join(lines)


def _install_pkg(pkg):
    if not shutil.which("apt"):
        return "apt not available — install packages via Sileo instead"
    if not pkg:
        return "Usage: @plugin tools install <package>"
    try:
        r = safe_exec(f"apt install -y {shlex.quote(pkg)}", timeout=120)
        if r["success"]:
            out = r["stdout"].strip()[-600:]
            return f"Installed {pkg}:\n{out}" if out else f"Installed {pkg}"
        else:
            err = (r["stderr"].strip() or r["stdout"].strip())[-400:]
            return f"Failed to install {pkg}:\n{err}"
    except Exception as e:
        return f"Error: {e}"


def run_tools(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "check":
        return _check_tools()
    elif subcmd == "install":
        pkg = parts[1].strip() if len(parts) > 1 else ""
        return _install_pkg(pkg)
    elif subcmd == "list":
        lines = ["Known tools:"]
        for name, desc in TOOLS_CHECK:
            status = "✅" if shutil.which(name) else "❌"
            lines.append(f"  {status} {name:<14} — {desc}")
        return "\n".join(lines)
    else:
        return TOOLS_HELP


SKILL = {
    "name": "tools",
    "description": "Check & install CLI tools — @plugin tools check | install <pkg> | list",
    "run": run_tools,
}
