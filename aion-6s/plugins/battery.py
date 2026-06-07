import re
import shutil
from core.jailbreak import safe_exec


def _ioreg_batt():
    """Read battery via ioreg (works on macOS, may work on jailbroken iOS)."""
    try:
        r = safe_exec("ioreg -w 0 -rc AppleSmartBattery", timeout=8)
        if not r["success"] or not r["stdout"].strip():
            return None
        out = r["stdout"]
        def get(k):
            m = re.search(rf'"{k}"\s*=\s*(\S+)', out)
            return m.group(1).rstrip(",") if m else "?"
        pct = float(get("CurrentCapacity")) / float(get("MaxCapacity")) * 100 if get("MaxCapacity") != "?" else "?"
        pct = f"{pct:.0f}" if isinstance(pct, float) else "?"
        charging = "charging" if get("IsCharging") == "Yes" else "discharging"
        return f"Battery: {pct}%, {charging}"
    except Exception:
        return None


def _pmset_batt():
    try:
        r = safe_exec("pmset -g batt", timeout=5)
        if not r["success"] and not r["stdout"]:
            return None
        output = r["stdout"] + r["stderr"]
        m = re.search(r'(\d+)%', output)
        pct = m.group(1) if m else "?"
        charging = "charging" if "charging" in output.lower() or "AC" in output or "connected" in output.lower() else "discharging"
        time_match = re.search(r'(\d+:\d+)', output)
        remaining = time_match.group(1) if time_match else "?"
        return f"Battery: {pct}%, {charging}, {remaining} remaining"
    except Exception:
        return None


def run_battery(args=""):
    if shutil.which("pmset"):
        result = _pmset_batt()
        if result:
            return result
    if shutil.which("ioreg"):
        result = _ioreg_batt()
        if result:
            return result
    return "Battery: not available on this device"


SKILL = {
    "name": "battery",
    "description": "Check battery status: percentage, charging, time remaining",
    "run": run_battery,
}
