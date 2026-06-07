import re

from core.ios_hw import ioreg_get_first, ioreg_get_properties
from core.jailbreak import safe_exec


def _thermal_via_armpmu():
    services = ioreg_get_properties("AppleARMPMU")
    if not services:
        return None
    sensors = []
    for svc in services:
        for k, v in svc.items():
            if isinstance(v, (int, float)) and 'temp' in k.lower():
                sensors.append(('Temperature', k, f"{v:.1f}"))
            elif isinstance(v, (int, float)) and 'volt' in k.lower():
                sensors.append(('Voltage', k, f"{v:.3f}V"))
            elif isinstance(v, (int, float)) and 'curr' in k.lower():
                sensors.append(('Current', k, f"{v:.3f}A"))
    if not sensors:
        return None
    return sensors


def _als_via_iokit():
    props = ioreg_get_first("AppleEmbeddedI2CLightSensor")
    if not props:
        return None
    for k in ('illuminance', 'ALS_LEVEL', 'lightSensorValue'):
        v = props.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return None


def _spu_sensors():
    services = ioreg_get_properties("AppleSPUHIDDevice")
    if not services:
        services = ioreg_get_properties("AppleSPU")
    if not services:
        return None
    result = {}
    for svc in services:
        name = svc.get('name', '').lower()
        if 'accel' in name:
            vals = {}
            for ax in ('x', 'y', 'z'):
                v = svc.get(ax.upper()) or svc.get(ax)
                if v is not None:
                    vals[ax] = str(v)
            if vals:
                result['accel'] = vals
        elif 'gyro' in name:
            vals = {}
            for ax in ('x', 'y', 'z'):
                v = svc.get(ax.upper()) or svc.get(ax)
                if v is not None:
                    vals[ax] = str(v)
            if vals:
                result['gyro'] = vals
        elif 'pressure' in name or 'baro' in name:
            pressure = svc.get('pressure') or svc.get('barometricPressure')
            if pressure is not None:
                result['barometer'] = {'pressure': str(pressure)}
            temp = svc.get('temperature') or svc.get('temp')
            if temp is not None:
                result.setdefault('barometer', {})['temp'] = str(temp)
    return result if result else None


def _thermal_shell():
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
            data.setdefault(section, []).append((m.group(1).strip(), m.group(2)))
            continue
        m = re.match(r"(.+?):\s+([\d.]+)\s*V?", stripped)
        if m and section == "voltages":
            data.setdefault(section, []).append((m.group(1).strip(), m.group(2)))
            continue
        m = re.match(r"(.+?):\s+([\d.]+)\s*A?", stripped)
        if m and section == "currents":
            data.setdefault(section, []).append((m.group(1).strip(), m.group(2)))
    return {k: v for k, v in data.items() if v} or None


def run_sensors(args=""):
    args = (args or "").strip().lower()

    if args in ("--all", "-a"):
        parts = []
        spu = _spu_sensors()
        if spu:
            parts.append(_format_spu(spu))
        als = _als_via_iokit()
        if als is not None:
            parts.append(f"Ambient Light: {als} lux")
        thermal = _thermal_via_armpmu()
        if thermal:
            parts.append(_format_armpmu(thermal))
        else:
            thermal2 = _thermal_shell()
            if thermal2:
                parts.append(_format_thermal_shell(thermal2))
        return "\n\n".join(parts) if parts else "No sensors available."

    if args in ("--thermal", "-t"):
        thermal = _thermal_via_armpmu()
        if thermal:
            return _format_armpmu(thermal)
        thermal2 = _thermal_shell()
        if thermal2:
            return _format_thermal_shell(thermal2)
        return ("Thermal sensors unavailable — install 'sensors' from Flobul repo via Sileo.")

    if args in ("--accel", "-c"):
        spu = _spu_sensors()
        if spu and "accel" in spu:
            a = spu["accel"]
            return f"Accelerometer: X={a.get('x','?')} Y={a.get('y','?')} Z={a.get('z','?')}"
        return "Accelerometer unavailable."

    if args in ("--ioreg", "-i"):
        parts = []
        spu = _spu_sensors()
        if spu:
            parts.append(_format_spu(spu))
        als = _als_via_iokit()
        if als is not None:
            parts.append(f"Ambient Light: {als} lux")
        thermal = _thermal_via_armpmu()
        if thermal:
            parts.append(_format_armpmu(thermal))
        return "\n\n".join(parts) if parts else "IOKit sensors unavailable."

    spu = _spu_sensors()
    als = _als_via_iokit()
    thermal = _thermal_via_armpmu()
    lines = []
    if spu:
        lines.append(_format_spu(spu))
    if als is not None:
        lines.append(f"Ambient Light: {als} lux")
    if thermal:
        lines.append(_format_armpmu(thermal))
    else:
        thermal2 = _thermal_shell()
        if thermal2:
            lines.append(_format_thermal_shell(thermal2))
    if not lines:
        return ("Sensors unavailable. Install:\n"
                "  - sensors via Sileo (Flobul repo)")
    return "\n\n".join(lines)


def _format_spu(data):
    lines = ["AOP HID Sensors:"]
    if "accel" in data:
        a = data["accel"]
        lines.append(f"  Accelerometer: X={a.get('x','?')} Y={a.get('y','?')} Z={a.get('z','?')}")
    if "gyro" in data:
        g = data["gyro"]
        lines.append(f"  Gyroscope: X={g.get('x','?')} Y={g.get('y','?')} Z={g.get('z','?')}")
    if "barometer" in data:
        b = data["barometer"]
        lines.append(f"  Barometer: {b.get('pressure', '?')} Pa")
        if b.get("temp"):
            lines.append(f"  Baro Temp: {b['temp']}°C")
    return "\n".join(lines)


def _format_armpmu(data):
    lines = ["Thermal Sensors (AppleARMPMU):"]
    for kind, name, val in data:
        lines.append(f"  {name}: {val}")
    return "\n".join(lines)


def _format_thermal_shell(data):
    lines = ["Thermal Sensors (Flobul/Sensors):"]
    if "thermals" in data:
        for name, val in data["thermals"]:
            lines.append(f"  {name}: {val}°C")
    if "voltages" in data:
        lines.append("  --- Voltages ---")
        for name, val in data["voltages"]:
            lines.append(f"  {name}: {val}V")
    if "currents" in data:
        lines.append("  --- Currents ---")
        for name, val in data["currents"]:
            lines.append(f"  {name}: {val}A")
    return "\n".join(lines)


SKILL = {
    "name": "sensors",
    "description": "Read onboard sensors — accelerometer, gyroscope, barometer, ALS, thermal, voltage, current via IOKit ctypes. Args: --all, --thermal, --accel, --ioreg",
    "run": run_sensors,
    "args": True,
}
