import json
import logging
from core.ios_hw import ioreg_get_first
from core.jailbreak import safe_exec

LOGGER = logging.getLogger(__name__)


def _get_battery_props():
    props = ioreg_get_first("AppleARMPMU")
    if props:
        for k in ("BatteryInstalled", "CurrentCapacity", "MaxCapacity",
                   "CycleCount", "Temperature", "Voltage", "IsCharging",
                   "AppleRawCurrentCapacity", "AppleRawMaxCapacity"):
            if k in props:
                return props
    return ioreg_get_first("AppleSmartBattery")


def _mcp_battery():
    """Fallback: query local MCP server for battery info (works as mobile user)."""
    import urllib.request
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_device_info", "arguments": {}}}).encode()
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8090/mcp",
                data=payload, headers={"Content-Type": "application/json"}),
            timeout=5)
        d = json.loads(resp.read())
        for c in d.get("result", {}).get("content", []):
            if c.get("type") == "text":
                dev = json.loads(c["text"])
                pct = dev.get("batteryLevel")
                state = dev.get("batteryState", "unknown")
                if pct is not None:
                    return f"Battery: {pct:.0f}%  {state}"
    except Exception:
        LOGGER.debug("mcp battery fallback failed")
    return None


def run_battery(args=""):
    props = _get_battery_props()
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

    mcp = _mcp_battery()
    if mcp:
        return mcp

    return "Battery: not available on this device"


SKILL = {
    "name": "battery",
    "description": "Check battery status: percentage, charging, time remaining",
    "run": run_battery,
}
