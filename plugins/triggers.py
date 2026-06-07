import logging
import os
import json
import fnmatch
from core.jailbreak import safe_exec
from core.guardrails import check as guard_check

LOGGER = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "triggers.json",
)

DEFAULT_RULES = {
    "wifi_joined": {"action": "notify", "value": "WiFi connected"},
    "wifi_left": {"action": "notify", "value": "WiFi disconnected"},
    "power_connected": {"action": "notify", "value": "Now charging"},
    "power_disconnected": {"action": "notify", "value": "On battery"},
    "lock": {"action": "ignore"},
    "unlock": {"action": "notify", "value": "Device unlocked"},
    "low_battery": {"action": "ai", "value": "low_battery"},
}

HELP = """\
Trigger engine — autonomous event to action rules.
Config: triggers.json in project root.

Usage:
  @plugin triggers list                   — show all rules
  @plugin triggers add <event> <action> [value]  — add rule
  @plugin triggers remove <event>         — remove rule
  @plugin triggers reload                 — reload config from disk
  @plugin triggers test <event>           — test a rule without waiting for event

Actions:
  cmd <command>        — execute shell command
  notify <text>        — log message
  notify_post <name>   — send Darwin notification
  ai <prompt>          — forward event to AI
  ignore               — silently skip

Events: wifi_joined, wifi_left, power_connected, power_disconnected,
        lock, unlock, low_battery, hourly, or any Activator event.
        Supports wildcards: activator.* matches all Activator events.
"""


def _load():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                return json.load(f)
    except Exception:
        LOGGER.debug("triggers config load failed")
    return {}


def _save(rules):
    tmp = CONFIG_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(rules, f, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except Exception:
        return False


def _ensure_defaults():
    if not os.path.exists(CONFIG_PATH):
        _save(DEFAULT_RULES)


def run_triggers(args=""):
    parts = args.strip().split(None, 2)
    subcmd = parts[0].lower() if parts else ""
    arg1 = parts[1].strip() if len(parts) > 1 else ""
    arg2 = parts[2].strip() if len(parts) > 2 else ""

    if subcmd == "list":
        _ensure_defaults()
        rules = _load()
        lines = [f"Trigger rules ({len(rules)}):"]
        for event, cfg in sorted(rules.items()):
            action = cfg.get("action", "?")
            value = cfg.get("value", "")
            if value:
                lines.append(f"  {event} -> {action} {value}")
            else:
                lines.append(f"  {event} -> {action}")
        return "\n".join(lines)

    if subcmd == "add":
        if not arg1 or not arg2:
            return "Usage: @plugin triggers add <event> <action> [value]"
        sub_parts = arg2.split(None, 1)
        action = sub_parts[0].lower()
        value = sub_parts[1] if len(sub_parts) > 1 else ""
        valid = ("cmd", "notify", "notify_post", "ai", "ignore")
        if action not in valid:
            return f"Invalid action: {action}. Valid: {', '.join(valid)}"
        rules = _load()
        rules[arg1] = {"action": action}
        if value:
            rules[arg1]["value"] = value
        if _save(rules):
            return f"Added: {arg1} -> {action} {value}"
        return "Failed to save triggers.json"

    if subcmd == "remove":
        if not arg1:
            return "Usage: @plugin triggers remove <event>"
        rules = _load()
        if arg1 in rules:
            del rules[arg1]
            if _save(rules):
                return f"Removed: {arg1}"
            return "Failed to save triggers.json"
        return f"Rule '{arg1}' not found"

    if subcmd == "reload":
        _ensure_defaults()
        rules = _load()
        return f"Reloaded {len(rules)} trigger rules"

    if subcmd == "process":
        _ensure_defaults()
        rules = _load()
        event = arg1 or ""
        for pattern, cfg in rules.items():
            if fnmatch.fnmatch(event, pattern):
                action = cfg.get("action", "ignore")
                value = cfg.get("value", "")
                if action == "ai":
                    return "ai"
                if action == "ignore":
                    return ""
                if action == "cmd":
                    blocked, _ = guard_check(value)
                    if blocked:
                        return f"handled|blocked|{blocked}"
                    r = safe_exec(value, timeout=30)
                    status = "OK" if r["success"] else r["stderr"][:100]
                    return f"handled|{action}|{value}|{status}"
                if action == "notify":
                    return f"handled|{action}|{value}"
                if action == "notify_post":
                    _notify_post(value)
                    return f"handled|{action}|{value}"
                return f"handled|{action}|{value}"
        return ""

    if subcmd == "test":
        if not arg1:
            return "Usage: @plugin triggers test <event>"
        return run_triggers(f"process {arg1}")

    return HELP


def _notify_post(name):
    if not name:
        return
    try:
        import ctypes
        import ctypes.util
        libc_path = ctypes.util.find_library("c")
        if not libc_path:
            return
        libc = ctypes.cdll.LoadLibrary(libc_path)
        libc.notify_post.argtypes = [ctypes.c_char_p]
        libc.notify_post(name.encode())
    except Exception:
        LOGGER.debug("notify_post failed")


SKILL = {
    "name": "triggers",
    "description": "Event->action rules. @plugin triggers list|add|remove|reload|test <event>",
    "run": run_triggers,
}
