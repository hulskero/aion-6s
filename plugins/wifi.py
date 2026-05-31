import subprocess
import re
import shutil


def _ifconfig_en0():
    """Basic WiFi info from ifconfig (always works, no extra packages)."""
    try:
        r = subprocess.run(["ifconfig", "en0"], capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            return {}
        out = r.stdout
        data = {}
        m = re.search(r'status:\s*(\S+)', out)
        data["status"] = m.group(1) if m else "unknown"
        m = re.search(r'ether\s+([0-9a-f:]+)', out)
        data["mac"] = m.group(1) if m else "?"
        m = re.search(r'inet\s+(\S+)', out)
        data["ip"] = m.group(1) if m else "?"
        return data
    except Exception:
        return {}


def _ioreg_wifi():
    """Extended WiFi info via ioreg (requires IOKitTools package)."""
    if not shutil.which("ioreg"):
        return None
    try:
        r = subprocess.run(
            ["ioreg", "-rc", "IO80211Interface"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        out = r.stdout
        data = {}
        def get(k):
            m = re.search(rf'"{k}"\s*=\s*(\S+)', out)
            if m:
                return m.group(1).rstrip(",")
            m = re.search(rf'"{k}"\s*=\s*"([^"]*)"', out)
            return m.group(1) if m else None
        for key in ("SSID", "BSSID", "RSSI", "channel", "noise", "txRate"):
            v = get(key)
            if v is not None:
                data[key.lower()] = v
        if not data:
            return None
        return data
    except Exception:
        return None


def run_wifi(args=""):
    basic = _ifconfig_en0()
    if not basic:
        return "WiFi: en0 not available"
    ext = _ioreg_wifi()
    lines = []
    if ext:
        parts = []
        if "ssid" in ext:
            parts.append(f"SSID: {ext['ssid']}")
        if "bssid" in ext:
            parts.append(f"BSSID: {ext['bssid']}")
        if "rssi" in ext:
            parts.append(f"RSSI: {ext['rssi']} dBm")
        if "channel" in ext:
            parts.append(f"CH: {ext['channel']}")
        if "noise" in ext:
            parts.append(f"Noise: {ext['noise']} dBm")
        if "txrate" in ext:
            parts.append(f"TX: {ext['txrate']} Mbps")
        lines.append("  ".join(parts))
    else:
        lines.append("Extended info unavailable (install IOKitTools via Sileo)")
    ip = basic.get("ip", "?")
    mac = basic.get("mac", "?")
    status = basic.get("status", "?")
    lines.append(f"IP: {ip}  MAC: {mac}  Status: {status}")
    return "\n".join(lines)


SKILL = {
    "name": "wifi",
    "description": "WiFi status — SSID, BSSID, RSSI, channel, IP (requires IOKitTools for SSID/RSSI)",
    "run": run_wifi,
}
