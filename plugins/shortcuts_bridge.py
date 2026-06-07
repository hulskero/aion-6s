import shutil
import urllib.parse
import subprocess as sp


HELP_TEXT = """\
Shortcuts Bridge — run/list Shortcuts from CLI.

iPhone 6s limitations:
  - 'shortcuts' CLI does not exist on iOS (macOS only)
  - URL scheme (shortcuts://) works but is fire-and-forget (no output)
  - SpringCuts (repo.anthopak.dev) enables output capture

Usage:
  @plugin shortcuts_bridge run <name> [input]
  @plugin shortcuts_bridge list
  @plugin shortcuts_bridge open <name>
"""


def _via_url(name, inp=""):
    url = f"shortcuts://run-shortcut?name={urllib.parse.quote(name, safe='')}"
    if inp:
        url += f"&input=text&text={urllib.parse.quote(inp, safe='')}"
    if not shutil.which("open"):
        return None
    try:
        sp.run(["open", url], capture_output=True, timeout=5)
    except Exception:
        pass
    return {"text": f"Opened '{name}' via Shortcuts app (fire-and-forget, no output capture)"}


def _via_springcuts(name, inp=""):
    if not shutil.which("springcuts"):
        return None
    import shlex
    cmd = f'springcuts -r {shlex.quote(name)}'
    if inp:
        cmd += f' -p {shlex.quote(inp)}'
    cmd += ' -w'
    from core.jailbreak import safe_exec
    r = safe_exec(cmd, timeout=30)
    if r["success"] and r["stdout"].strip():
        return {"text": f"Shortcut '{name}':\n{r['stdout'][:2000]}"}
    return None


def _list():
    if shutil.which("springcuts"):
        from core.jailbreak import safe_exec
        r = safe_exec("springcuts -l", timeout=10)
        if r["success"] and r["stdout"].strip():
            items = r["stdout"].strip().splitlines()
            lines = [f"Shortcuts ({len(items)}):"]
            for item in items[:50]:
                lines.append(f"  {item.strip()}")
            return {"text": "\n".join(lines)}
    return None


def run_shortcuts_bridge(args=""):
    parts = args.strip().split(None, 2)
    subcmd = parts[0].lower() if parts else ""
    name = parts[1].strip() if len(parts) > 1 else ""
    inp = parts[2].strip() if len(parts) > 2 else ""

    if subcmd == "list":
        result = _list()
        if result:
            return result["text"]
        return "No shortcuts found. Install SpringCuts (repo.anthopak.dev) for list support."

    if subcmd == "run":
        if not name:
            return "Usage: @plugin shortcuts_bridge run <name> [input]"
        result = _via_springcuts(name, inp)
        if result:
            return result["text"]
        result = _via_url(name, inp)
        if result:
            return result["text"] + "\nInstall SpringCuts (repo.anthopak.dev) for output capture."
        return "Cannot run shortcuts: install SpringCuts (repo.anthopak.dev) for CLI support."

    if subcmd == "open":
        if not name:
            return "Usage: @plugin shortcuts_bridge open <name>"
        result = _via_url(name, inp)
        if result:
            return result["text"]
        return "open command not available."

    return HELP_TEXT


SKILL = {
    "name": "shortcuts_bridge",
    "description": "Shortcuts via URL scheme or SpringCuts (repo.anthopak.dev) — @plugin shortcuts_bridge run|list|open",
    "run": run_shortcuts_bridge,
}
