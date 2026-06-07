import shutil
import shlex
import urllib.parse
from core.jailbreak import safe_exec

HELP_TEXT = """\
Shortcuts Bridge — 2-way CLI for iOS Shortcuts.

Requirements:
  - SpringCuts (repo.anthopak.dev) for full output capture
  - OR 'shortcuts' CLI (comes with macOS, may need Procursus on iOS)

Usage:
  @plugin shortcuts_bridge run <name> [input]    — run shortcut, get output
  @plugin shortcuts_bridge list                  — list all shortcuts
  @plugin shortcuts_bridge open <name>           — open via x-callback-url

Examples:
  @plugin shortcuts_bridge run "AION Voice"
  @plugin shortcuts_bridge run "Get Weather" "Prague"
  @plugin shortcuts_bridge list

Setup for 'run' with output:
  If 'shortcuts' CLI not available, install SpringCuts:
    1. Add repo.anthopak.dev to Sileo
    2. Install springcuts
    3. Use: springcuts -r "Name" -w   # -w waits for output
"""


def _list_via_shortcuts():
    r = safe_exec("shortcuts list", timeout=10)
    if r["success"] and r["stdout"].strip():
        return r["stdout"].strip().splitlines()
    return None


def _list_via_springcuts():
    r = safe_exec("springcuts -l", timeout=10)
    if r["success"] and r["stdout"].strip():
        return r["stdout"].strip().splitlines()
    return None


def _run_via_springcuts(name, inp=""):
    if inp:
        cmd = f'springcuts -r {shlex.quote(name)} -p {shlex.quote(inp)} -w'
    else:
        cmd = f'springcuts -r {shlex.quote(name)} -w'
    r = safe_exec(cmd, timeout=30)
    return r


def _run_via_url(name, inp=""):
    import subprocess
    url = f"shortcuts://run-shortcut?name={urllib.parse.quote(name, safe='')}"
    if inp:
        url += f"&input=text&text={urllib.parse.quote(inp, safe='')}"
    if not shutil.which("open"):
        return {"success": False, "stdout": "", "stderr": "open not available", "code": -1}
    try:
        subprocess.run(["open", url], capture_output=True, timeout=5)
    except Exception:
        pass
    return {"success": True, "stdout": f"Opened {name} via x-callback-url", "stderr": ""}


def run_shortcuts_bridge(args=""):
    parts = args.strip().split(None, 2)
    subcmd = parts[0].lower() if parts else ""
    name = parts[1].strip() if len(parts) > 1 else ""
    inp = parts[2].strip() if len(parts) > 2 else ""

    if subcmd == "list":
        items = _list_via_shortcuts() or _list_via_springcuts()
        if items:
            lines = [f"Shortcuts ({len(items)}):"]
            for item in items[:50]:
                clean = item.strip().replace("✅", "").replace("❌", "").strip()
                lines.append(f"  {clean}")
            return "\n".join(lines)
        return "No shortcuts found. Install SpringCuts (repo.anthopak.dev) for list support."

    if subcmd == "run":
        if not name:
            return "Usage: @plugin shortcuts_bridge run <name> [input]"
        has_springcuts = shutil.which("springcuts")
        has_shortcuts = shutil.which("shortcuts")
        if has_springcuts:
            r = _run_via_springcuts(name, inp)
            if r["success"] and r["stdout"].strip():
                return f"Shortcut '{name}':\n{r['stdout'][:2000]}"
        if has_shortcuts:
            r = safe_exec(f"shortcuts run {shlex.quote(name)}", timeout=30)
            if r["success"]:
                return f"Shortcut '{name}' completed."
        # Fallback: x-callback-url
        _run_via_url(name, inp)
        return (f"Opened '{name}' via URL. Install SpringCuts "
                "(repo.anthopak.dev) for CLI output capture.")

    if subcmd == "open":
        if not name:
            return "Usage: @plugin shortcuts_bridge open <name>"
        _run_via_url(name, inp)
        return f"Opened '{name}' via Shortcuts app."

    return HELP_TEXT


SKILL = {
    "name": "shortcuts_bridge",
    "description": "2-way Shortcuts bridge via SpringCuts — @plugin shortcuts_bridge run|list|open",
    "run": run_shortcuts_bridge,
}
