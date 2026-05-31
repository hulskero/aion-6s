import subprocess
import re
import shutil


def run_battery(args=""):
    if not shutil.which("pmset"):
        return "Battery: not available on this device (pmset not found)"
    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout + result.stderr
        m = re.search(r'(\d+)%', output)
        pct = m.group(1) if m else "?"
        charging = "charging" if "charging" in output.lower() or "AC" in output or "connected" in output.lower() else "discharging"
        time_match = re.search(r'(\d+:\d+)', output)
        remaining = time_match.group(1) if time_match else "?"
        return f"Battery: {pct}%, {charging}, {remaining} remaining"
    except Exception as e:
        return f"Battery: unavailable ({e})"


SKILL = {
    "name": "battery",
    "description": "Check battery status: percentage, charging, time remaining",
    "run": run_battery,
}
