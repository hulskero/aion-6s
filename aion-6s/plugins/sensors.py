import re
import json

from core.jailbreak import safe_exec


def _check_tool(name):
    r = safe_exec(f"which {name}", timeout=5)
    return r["success"]


def _ioreg_sensors():
    """Read onboard sensors via ioreg (accelerometer, barometer, ALS, Touch ID)."""
    data = {}
    probes = [
        ("accel", "ioreg -rc IMUDevice",
         lambda t: {"x": _ioreg_val(t, "X"), "y": _ioreg_val(t, "Y"), "z": _ioreg_val(t, "Z")}
         if any(_ioreg_val(t, k) for k in ("X", "Y", "Z")) else None),
        ("barometer", "ioreg -rc AppleBarometer",
         lambda t: {"pressure": _ioreg_val(t, "pressure"), "temp": _ioreg_val(t, "temperature")}
         if _ioreg_val(t, "pressure") else None),
        ("als", "ioreg -p IODeviceTree -r -n als",
         lambda t: {"illuminance": _ioreg_val(t, "illuminance")}
         if _ioreg_val(t, "illuminance") else None),
        ("touchid", "ioreg -rc AppleSEPKeyStore",
         lambda t: "present" if "finger" in t.lower() else None),
    ]
    for key, cmd, parser in probes:
        r = safe_exec(cmd, timeout=8)
        if r["success"] and r["stdout"].strip():
            val = parser(r["stdout"])
            if val is not None:
                data[key] = val
    return data if data else None


def _ioreg_val(text, key):
    m = re.search(rf'"{key}"\s*=\s*(\S+)', text)
    return m.group(1).rstrip(",") if m else None


def _thermal_sensors():
    """Read thermal/voltage/current sensors via 'sensors' CLI (Flobul/Sensors)."""
    r = safe_exec("sensors", timeout=8)
    if not r["success"] or not r["stdout"].strip():
        return None
    data = {"thermals": [], "voltages": [], "currents": []}
    section = "thermals"
    for line in r["stdout"].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if "voltage" in low:
            section = "voltages"
            continue
        if "current" in low:
            section = "currents"
            continue
        m = re.match(r"(.+?):\s+([\d.]+)\s*°?C?", stripped)
        if m:
            data.setdefault(section, []).append({"name": m.group(1).strip(), "value": m.group(2)})
            continue
        m = re.match(r"(.+?):\s+([\d.]+)\s*V?", stripped)
        if m and section == "voltages":
            data.setdefault(section, []).append({"name": m.group(1).strip(), "value": m.group(2)})
            continue
        m = re.match(r"(.+?):\s+([\d.]+)\s*A?", stripped)
        if m and section == "currents":
            data.setdefault(section, []).append({"name": m.group(1).strip(), "value": m.group(2)})
    # Remove empty sections
    return {k: v for k, v in data.items() if v}


def _ioprint_json():
    """Full IOKit state via ioprint -j (Siguza/iokit-utils)."""
    r = safe_exec("ioprint -j", timeout=10)
    if not r["success"] or not r["stdout"].strip():
        return None
    try:
        return json.loads(r["stdout"])
    except (json.JSONDecodeError, ValueError):
        return r["stdout"][:2000]


def run_sensors(args=""):
    args = (args or "").strip().lower()

    if args in ("--all", "-a"):
        parts = []
        ioreg = _ioreg_sensors()
        if ioreg:
            parts.append(_format_ioreg(ioreg))
        thermal = _thermal_sensors()
        if thermal:
            parts.append(_format_thermal(thermal))
        iop = _ioprint_json()
        if iop:
            if isinstance(iop, dict):
                parts.append(f"IOKit JSON: {json.dumps(iop, indent=2)[:1500]}")
            else:
                parts.append(f"IOKit raw:\n{iop}")
        return "\n\n".join(parts) if parts else "No sensors available."

    if args in ("--thermal", "-t"):
        thermal = _thermal_sensors()
        if thermal:
            return _format_thermal(thermal)
        r = safe_exec("sensors", timeout=8)
        if not r["success"]:
            return "Thermal sensors unavailable — install 'sensors' from Flobul repo via Sileo."
        return r["stdout"]

    if args in ("--accel", "-c"):
        ioreg = _ioreg_sensors()
        if ioreg and "accel" in ioreg:
            a = ioreg["accel"]
            return f"Accelerometer: X={a.get('x','?')} Y={a.get('y','?')} Z={a.get('z','?')}"
        return "Accelerometer unavailable."

    if args in ("--ioreg", "-i"):
        ioreg = _ioreg_sensors()
        if ioreg:
            return _format_ioreg(ioreg)
        return "IOKit sensors unavailable."

    # Default: show all available
    ioreg = _ioreg_sensors()
    thermal = _thermal_sensors()
    lines = []
    if ioreg:
        lines.append(_format_ioreg(ioreg))
    if thermal:
        lines.append(_format_thermal(thermal))
    if not lines:
        return ("Sensors unavailable. Install:\n"
                "  - IOKitTools via Sileo (Siguza repo)\n"
                "  - sensors via Sileo (Flobul repo)")
    return "\n\n".join(lines)


def _format_ioreg(data):
    lines = ["IOKit Sensors:"]
    if "accel" in data:
        a = data["accel"]
        lines.append(f"  Accelerometer: X={a.get('x','?')} Y={a.get('y','?')} Z={a.get('z','?')}")
    if "barometer" in data:
        b = data["barometer"]
        lines.append(f"  Barometer: {b.get('pressure', '?')} Pa")
        if b.get("temp"):
            lines.append(f"  Baro Temp: {b['temp']}°C")
    if "als" in data:
        lines.append(f"  Ambient Light: {data['als'].get('illuminance', '?')} lux")
    if "touchid" in data:
        lines.append("  Touch ID: present")
    return "\n".join(lines)


def _format_thermal(data):
    lines = ["Thermal Sensors (Flobul/Sensors):"]
    if "thermals" in data:
        for s in data["thermals"]:
            lines.append(f"  {s['name']}: {s['value']}°C")
    if "voltages" in data:
        lines.append("  --- Voltages ---")
        for s in data["voltages"]:
            lines.append(f"  {s['name']}: {s['value']}V")
    if "currents" in data:
        lines.append("  --- Currents ---")
        for s in data["currents"]:
            lines.append(f"  {s['name']}: {s['value']}A")
    return "\n".join(lines)


SKILL = {
    "name": "sensors",
    "description": "Read onboard sensors — accelerometer, barometer, ALS, Touch ID, thermal, voltage, current. Args: --all, --thermal, --accel, --ioreg",
    "run": run_sensors,
    "args": True,
}
