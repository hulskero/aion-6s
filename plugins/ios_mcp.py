import json
import shlex
import logging
from core.jailbreak import safe_exec

LOGGER = logging.getLogger(__name__)

MCP_URL = "http://127.0.0.1:8090/mcp"
_NEXT_ID = 1


def _mcp_call(method, params=None):
    global _NEXT_ID
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": _NEXT_ID,
        "method": method,
        **(params or {}),
    })
    _NEXT_ID += 1
    cmd = (
        f"curl -sS --connect-timeout 5 --max-time 15 "
        f"-X POST {shlex.quote(MCP_URL)} "
        f"-H 'Content-Type: application/json' "
        f"-d {shlex.quote(payload)}"
    )
    result = safe_exec(cmd, timeout=20)
    if not result["success"]:
        return {"error": result["stderr"][:500]}
    try:
        return json.loads(result["stdout"])
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"JSON parse: {e}", "raw": result["stdout"][:500]}


def _mcp_tool(name, args_dict=None):
    resp = _mcp_call("tools/call", {"params": {"name": name, "arguments": args_dict or {}}})
    if "error" in resp:
        return f"MCP error: {resp['error']}"
    content = resp.get("result", {}).get("content", [])
    parts = []
    for c in content:
        t = c.get("type", "")
        if t == "text":
            parts.append(c.get("text", ""))
        elif t == "image":
            parts.append(f"[image: {c.get('mimeType', '?')} {len(c.get('data', ''))} bytes]")
        else:
            parts.append(json.dumps(c)[:300])
    return "\n".join(parts) if parts else json.dumps(resp.get("result", {}), indent=2)[:3000]


def _mcp_tool_with_recovery(name, args_dict=None, timeout=15):
    """Call MCP tool with auto-recovery on timeout (AX-hang fix)."""
    import socket
    import subprocess
    try:
        return _mcp_tool(name, args_dict)
    except (socket.timeout, TimeoutError, OSError) as e:
        # AX subsystem may be hung — try to restart MCP daemon
        try:
            subprocess.run(
                ["launchctl", "kickstart", "-k", "system/com.aion.ios-mcp"],
                timeout=5, capture_output=True
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        # Retry once after restart
        try:
            return _mcp_tool(name, args_dict)
        except (socket.timeout, TimeoutError, OSError) as e2:
            return f"Error: {name} timeout (AX may be hung, restart daemon): {e2}"


def _mcp_list_tools():
    resp = _mcp_call("tools/list")
    if "error" in resp:
        return f"Error: {resp['error']}"
    tools = resp.get("result", {}).get("tools", [])
    if not tools:
        return "No tools available"
    lines = [f"MCP Tools ({len(tools)}):"]
    for t in tools:
        lines.append(f"  {t['name']} - {t['description'][:80]}")
    return "\n".join(lines)


def run_ios_mcp(args=""):
    args = args.strip()
    if not args:
        return (
            "Usage: @plugin ios_mcp <action> [args]\n\n"
            "Actions:\n"
            "  tools                  List MCP tools\n"
            "  info                   Device info\n"
            "  screen                 Screen info\n"
            "  app                    Frontmost app\n"
            "  ui [limit=N]           UI elements\n"
            "  screenshot             Take screenshot\n"
            "  describe               Describe screen\n"
            "  ocr                    OCR screen text\n"
            "  tap <x> <y>            Tap at coordinates\n"
            "  swipe <x1> <y1> <x2> <y2>  Swipe\n"
            "  type <text>            Type text\n"
            "  key <name>             Press key (enter,tab,delete,home,volup,voldn,power)\n"
            "  shell <command>        Run shell command via MCP\n"
            "  launch <bundle_id>     Launch app\n"
            "  kill <bundle_id>       Kill app\n"
            "  apps                   List user apps\n"
            "  running                List running apps\n"
            "  clipboard              Read clipboard\n"
            "  clipboard set <text>   Write clipboard\n"
            "  brightness [0-1]       Get/set brightness\n"
            "  volume [0-1]           Get/set volume\n"
            "  wake                   Wake and go home\n"
            "  home                   Press home button\n"
            "  log [sec=5]            Capture syslog\n"
            "  crash [bundle_id]      List crash reports\n"
            "  ls <path>              List directory\n"
            "  read <path>            Read file\n"
            "  call <tool> <json>     Raw MCP tool call"
        )

    parts = shlex.split(args)
    action = parts[0].lower()

    if action == "tools":
        return _mcp_list_tools()

    elif action == "info":
        return _mcp_tool_with_recovery("get_device_info")

    elif action == "screen":
        return _mcp_tool_with_recovery("get_screen_info")

    elif action == "app":
        return _mcp_tool_with_recovery("get_frontmost_app")

    elif action == "ui":
        limit = None
        for p in parts[1:]:
            if p.startswith("limit="):
                limit = int(p.split("=", 1)[1])
        params = {}
        if limit:
            params["limit"] = limit
        return _mcp_tool_with_recovery("get_ui_elements", params)

    elif action == "screenshot":
        return _mcp_tool_with_recovery("screenshot")

    elif action == "describe":
        return _mcp_tool_with_recovery("describe_screen", {"include_ocr": True})

    elif action == "ocr":
        return _mcp_tool_with_recovery("ocr_screen")

    elif action == "tap":
        if len(parts) < 3:
            return "Usage: @plugin ios_mcp tap <x> <y>"
        return _mcp_tool_with_recovery("tap_screen", {"x": int(parts[1]), "y": int(parts[2])})

    elif action == "swipe":
        if len(parts) < 5:
            return "Usage: @plugin ios_mcp swipe <fromX> <fromY> <toX> <toY>"
        return _mcp_tool_with_recovery("swipe_screen", {
            "fromX": int(parts[1]), "fromY": int(parts[2]),
            "toX": int(parts[3]), "toY": int(parts[4]),
        })

    elif action == "type":
        text = args[len("type"):].strip()
        return _mcp_tool_with_recovery("input_text", {"text": text})

    elif action == "key":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp key <name>"
        return _mcp_tool_with_recovery("press_key", {"key": parts[1]})

    elif action == "shell":
        cmd = args[len("shell"):].strip()
        if not cmd:
            return "Usage: @plugin ios_mcp shell <command>"
        return _mcp_tool_with_recovery("run_command", {"command": cmd, "timeout": 15})

    elif action == "launch":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp launch <bundle_id>"
        return _mcp_tool_with_recovery("launch_app", {"bundle_id": parts[1]})

    elif action == "kill":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp kill <bundle_id>"
        return _mcp_tool_with_recovery("kill_app", {"bundle_id": parts[1]})

    elif action == "apps":
        return _mcp_tool_with_recovery("list_apps", {"type": "user"})

    elif action == "running":
        return _mcp_tool_with_recovery("list_running_apps")

    elif action == "clipboard":
        if len(parts) >= 2 and parts[1] == "set":
            text = args[len("clipboard set"):].strip()
            return _mcp_tool_with_recovery("set_clipboard", {"text": text})
        return _mcp_tool_with_recovery("get_clipboard")

    elif action in ("brightness", "volume"):
        if len(parts) >= 2:
            try:
                val = float(parts[1])
                tool = "set_brightness" if action == "brightness" else "set_volume"
                return _mcp_tool_with_recovery(tool, {"level": val})
            except ValueError:
                pass
        tool = "get_brightness" if action == "brightness" else "get_volume"
        resp = _mcp_tool_with_recovery(tool)
        return resp

    elif action == "wake":
        return _mcp_tool_with_recovery("wake_and_home")

    elif action == "home":
        return _mcp_tool_with_recovery("press_home")

    elif action == "log":
        sec = int(parts[1]) if len(parts) >= 2 else 5
        return _mcp_tool_with_recovery("get_syslog", {"last_seconds": min(sec, 30)})

    elif action == "crash":
        bundle = parts[1] if len(parts) >= 2 else None
        params = {}
        if bundle:
            params["bundle_id"] = bundle
        return _mcp_tool_with_recovery("get_crash_logs", params)

    elif action == "ls":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp ls <path>"
        return _mcp_tool_with_recovery("list_dir", {"path": parts[1]})

    elif action == "read":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp read <path>"
        return _mcp_tool_with_recovery("read_file", {"path": parts[1]})

    elif action == "call":
        if len(parts) < 2:
            return "Usage: @plugin ios_mcp call <tool> [json_args]"
        tool_name = parts[1]
        try:
            call_args = json.loads(" ".join(parts[2:])) if len(parts) > 2 else {}
        except json.JSONDecodeError as e:
            return f"Invalid JSON args: {e}"
        return _mcp_tool_with_recovery(tool_name, call_args)

    elif action == "press_home":
        return _mcp_tool_with_recovery("press_home", {})

    elif action == "press_power":
        return _mcp_tool_with_recovery("press_power", {})

    elif action == "volume_up":
        return _mcp_tool_with_recovery("volume_up", {})

    elif action == "volume_down":
        return _mcp_tool_with_recovery("volume_down", {})

    elif action == "wake_and_home":
        return _mcp_tool_with_recovery("wake_and_home", {})

    elif action == "set_brightness":
        rest = args[len("set_brightness"):].strip()
        sub_parts = rest.split()
        if not sub_parts:
            return "Usage: set_brightness <0-100>"
        try:
            level = int(sub_parts[0])
        except ValueError:
            return f"Error: invalid level: {sub_parts[0]}"
        return _mcp_tool_with_recovery("set_brightness", {"level": level})

    elif action == "set_volume":
        rest = args[len("set_volume"):].strip()
        sub_parts = rest.split()
        if not sub_parts:
            return "Usage: set_volume <0-100>"
        try:
            level = int(sub_parts[0])
        except ValueError:
            return f"Error: invalid level: {sub_parts[0]}"
        return _mcp_tool_with_recovery("set_volume", {"level": level})

    elif action == "open_url":
        rest = args[len("open_url"):].strip()
        sub_parts = rest.split()
        if not sub_parts:
            return "Usage: open_url <url>"
        url = sub_parts[0]
        return _mcp_tool_with_recovery("open_url", {"url": url})

    elif action == "list_apps":
        return _mcp_tool_with_recovery("list_apps", {})

    elif action == "running_apps":
        return _mcp_tool_with_recovery("running_apps", {})

    else:
        return f"Unknown action: {action}. Try @plugin ios_mcp for help"


SKILL = {
    "name": "ios_mcp",
    "description": "Control iPhone via MCP — screenshot, tap, swipe, shell, apps, UI, OCR",
    "run": run_ios_mcp,
}
