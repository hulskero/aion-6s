import subprocess
import os
import time

CLIPBOARD_FILE = os.path.expanduser("~/Library/Caches/com.apple.Pasteboard/General")
CLIPBOARD_FILE2 = os.path.expanduser("~/Documents/aion_voice.txt")

HELP_TEXT = """\
Voice input via clipboard bridge.

Setup:
  1. Create an iOS Shortcut named "AION Voice":
     - Dictate Text (language: Czech or English)
     - Set Clipboard to dictated text
     - Write text to ~/Documents/aion_voice.txt
  2. Trigger via:
     - Siri: "Hey Siri, AION Voice"
     - Activator: double-press home → run Shortcut
     - Control Center: add Shortcuts widget

Usage:
  @plugin voice read              — read clipboard content
  @plugin voice trigger           — open Shortcuts dictation
  @plugin voice listen [sec]      — poll clipboard for N seconds,
                                    return first non-empty text
"""


def _clipboard_via_file():
    if os.path.exists(CLIPBOARD_FILE2):
        try:
            data = open(CLIPBOARD_FILE2).read().strip()
            if data:
                return data
        except Exception:
            pass
    return None


def _clipboard_via_pbpaste():
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def run_voice(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else "read"
    arg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd == "read":
        text = _clipboard_via_pbpaste() or _clipboard_via_file()
        if text:
            return f"Clipboard: {text[:1000]}"
        return "Clipboard empty or unavailable."

    if subcmd == "trigger":
        try:
            subprocess.run(
                ["open", "shortcuts://run-shortcut?name=AION%20Voice&input=text"],
                capture_output=True, timeout=5
            )
            return "Opened Shortcuts dictation. Speak now, then check with @plugin voice read"
        except Exception as e:
            return f"Failed: {e}"

    if subcmd == "listen":
        try:
            seconds = int(arg) if arg else 15
        except ValueError:
            seconds = 15
        deadline = time.time() + seconds
        while time.time() < deadline:
            text = _clipboard_via_pbpaste() or _clipboard_via_file()
            if text:
                return text[:2000]
            time.sleep(1)
        return "No voice input received within timeout."

    return HELP_TEXT


SKILL = {
    "name": "voice",
    "description": "Voice dictation via clipboard — @plugin voice read|trigger|listen [sec]",
    "run": run_voice,
}
