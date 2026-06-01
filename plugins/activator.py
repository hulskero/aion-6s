from core.jailbreak import safe_exec

ACTIVATOR_EVENTS = [
    "libactivator.system.wifi.joined",
    "libactivator.system.wifi.left",
    "libactivator.system.power.connected",
    "libactivator.system.power.disconnected",
    "libactivator.system.lock",
    "libactivator.system.unlock",
    "libactivator.system.bluetooth.joined",
    "libactivator.system.bluetooth.left",
    "libactivator.system.hourly",
    "libactivator.system.dawn",
    "libactivator.system.dusk",
    "libactivator.system.daylight",
    "libactivator.screen.dim",
    "libactivator.screen.wake",
    "libactivator.audio.headphones.connected",
    "libactivator.audio.headphones.disconnected",
]

HELP_TEXT = """\
Activator integration for jailbroken iOS.
Requires Activator (rpetri.ch/repo) and libactivator.

Usage:
  @plugin activator send <event>     — fire an Activator event
  @plugin activator list             — list common event names
  @plugin activator listen           — write AION FIFO path to Activator's Run Command

Examples:
  @plugin activator send libactivator.system.wifi.joined
  @plugin activator send libactivator.system.power.connected

Setup for auto-trigger:
  1. Activator → select trigger (e.g. WiFi Joined)
  2. Action → Run Command → set to:
     echo "event:wifi_joined" > /tmp/aion.event
  3. In AION: use /event command to process events

Available events for Activator:
  wifi.joined / wifi.left / power.connected / power.disconnected
  lock / unlock / bluetooth.joined / bluetooth.left
  hourly / dawn / dusk / screen.dim / screen.wake
"""


def _check_tool():
    r = safe_exec("which activator", timeout=5)
    return r["success"]


def run_activator(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd == "list":
        lines = ["Common Activator events:"]
        for ev in ACTIVATOR_EVENTS:
            name = ev.replace("libactivator.system.", "")
            lines.append(f"  {ev}  ({name})")
        return "\n".join(lines)

    if subcmd == "send":
        if not arg:
            return "Usage: @plugin activator send <event_name>"
        if not _check_tool():
            return "activator CLI not found — install from rpetri.ch/repo via Sileo"
        r = safe_exec(f"activator send {arg}", timeout=5)
        if r["success"]:
            return f"Sent: {arg}"
        return f"Failed: {r['stderr'][:200] or 'activator not configured'}"

    if subcmd == "listen":
        return ("To connect Activator → AION:\n"
                "  1. Open Activator → pick a trigger (e.g. Power Connected)\n"
                "  2. Action → Run Command → enter:\n"
                '     echo "event:system_event" > /tmp/aion.state\n'
                "  3. In AION run: /event start\n"
                "  4. To test: @plugin activator send <event>\n\n"
                "  notify_post com.aion.event  (optional, for zero-poll IPC)")

    return HELP_TEXT


SKILL = {
    "name": "activator",
    "description": "Send and receive Activator events — @plugin activator send|list|listen",
    "run": run_activator,
}
