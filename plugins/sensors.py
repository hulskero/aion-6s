import subprocess
import re
import shutil


def _ioreg_sensors():
    """Read onboard sensors via ioreg (requires IOKitTools)."""
    if not shutil.which("ioreg"):
        return None
    data = {}
    try:
        r = subprocess.run(
            ["ioreg", "-rc", "IMUDevice"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout
            def _get(k):
                m = re.search(rf'"{k}"\s*=\s*(\S+)', out)
                return m.group(1).rstrip(",") if m else None
            for key in ("X", "Y", "Z"):
                v = _get(key)
                if v:
                    data.setdefault("accel", {})[key.lower()] = v
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["ioreg", "-rc", "AppleBarometer"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0 and r.stdout.strip():
            m = re.search(r'"pressure"\s*=\s*(\S+)', r.stdout)
            if m:
                data["barometer"] = m.group(1).rstrip(",")
            m = re.search(r'"temperature"\s*=\s*(\S+)', r.stdout)
            if m:
                data["baro_temp"] = m.group(1).rstrip(",")
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["ioreg", "-p", "IODeviceTree", "-r", "-n", "als"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0 and r.stdout.strip():
            m = re.search(r'"illuminance"\s*=\s*(\S+)', r.stdout)
            if m:
                data["als"] = m.group(1).rstrip(",")
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["ioreg", "-rc", "AppleSEPKeyStore"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0 and "finger" in r.stdout.lower():
            data["touchid"] = "present"
    except Exception:
        pass
    if not data:
        return None
    return data


def run_sensors(args=""):
    data = _ioreg_sensors()
    if data is None:
        return ("Sensors unavailable — install IOKitTools via Sileo, "
                "then @plugin tools install iokittools")
    lines = ["Sensor Data:"]
    if "accel" in data:
        a = data["accel"]
        lines.append(f"  Accelerometer: X={a.get('x','?')} Y={a.get('y','?')} Z={a.get('z','?')}")
    if "barometer" in data:
        lines.append(f"  Barometer: {data['barometer']} Pa")
    if "baro_temp" in data:
        lines.append(f"  Baro Temp: {data['baro_temp']}°C")
    if "als" in data:
        lines.append(f"  Ambient Light: {data['als']} lux")
    if "touchid" in data:
        lines.append("  Touch ID: present")
    if len(lines) == 1:
        lines.append("  (no sensors detected)")
    return "\n".join(lines)


SKILL = {
    "name": "sensors",
    "description": "Read onboard sensors — accelerometer, barometer, ALS, Touch ID (needs IOKitTools)",
    "run": run_sensors,
}
