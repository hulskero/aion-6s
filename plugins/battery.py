import logging
from core.ios_hw import ioreg_get_first
from core.jailbreak import safe_exec

LOGGER = logging.getLogger(__name__)


def run_battery(args=""):
    props = ioreg_get_first("AppleSmartBattery")
    if props:
        installed = props.get("BatteryInstalled")
        if installed is False:
            return "Battery: not available"

        cur = props.get("AppleRawCurrentCapacity")
        maxc = props.get("AppleRawMaxCapacity")
        design = props.get("DesignCapacity")
        cycles = props.get("CycleCount")
        charging = props.get("IsCharging")
        temp = props.get("Temperature")
        voltage = props.get("Voltage")

        maxc_f = float(maxc) if maxc not in (None, "") else 0
        cur_f = float(cur) if cur not in (None, "") else 0
        pct = f"{cur_f / maxc_f * 100:.0f}%" if (cur_f and maxc_f > 0) else "?"
        state = "charging" if charging else "discharging"
        parts = [f"Battery: {pct}", state]

        if cycles is not None:
            parts.append(f"{int(cycles)} cycles")
        if temp is not None:
            try:
                tv = float(temp)
                if tv > 100:
                    tv /= 100
                parts.append(f"{tv:.1f}°C")
            except (ValueError, TypeError):
                parts.append(f"temp={temp}")
        if voltage is not None:
            try:
                vv = float(voltage)
                if vv > 100:
                    vv /= 1000
                parts.append(f"{vv:.3f}V")
            except (ValueError, TypeError):
                parts.append(f"voltage={voltage}")
        if design:
            parts.append(f"design={design}mAh")

        return "  ".join(parts)

    try:
        r = safe_exec("ioreg -rc AppleSmartBattery -w 0", timeout=8)
        if r["success"] and r["stdout"].strip():
            out = r["stdout"]

            def g(k):
                m = __import__('re').search(rf'"{k}"\s*=\s*(\S+)', out)
                return m.group(1).rstrip(",") if m else None

            cur, maxc = g("AppleRawCurrentCapacity"), g("AppleRawMaxCapacity")
            pct = f"{float(cur) / float(maxc) * 100:.0f}%" if (cur and maxc and float(maxc) > 0) else "?"
            state = "charging" if g("IsCharging") == "Yes" else "discharging"
            parts = [f"Battery: {pct}", state]
            for k in ("CycleCount", "Temperature", "Voltage"):
                v = g(k)
                if v:
                    parts.append(f"{k}: {v}")
            return "  ".join(parts)
    except Exception:
        LOGGER.debug("battery ioreg failed")

    return "Battery: not available on this device"


SKILL = {
    "name": "battery",
    "description": "Check battery status: percentage, charging, time remaining",
    "run": run_battery,
}
