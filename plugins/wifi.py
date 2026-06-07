import re

from core.ios_hw import ioreg_get_first
from core.jailbreak import safe_exec


def _ifconfig_en0():
    try:
        r = safe_exec("ifconfig en0", timeout=8)
        if not r["success"]:
            return {}
        out = r["stdout"]
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
    props = ioreg_get_first("IO80211Interface")
    if props:
        data = {}
        for src, dst in [
            ("SSID_STR", "ssid"), ("SSID", "ssid"),
            ("BSSID", "bssid"), ("RSSI", "rssi"),
            ("CHANNEL", "channel"), ("NOISE", "noise"),
            ("txRate", "txrate"), ("maxLinkSpeed", "maxspeed"),
        ]:
            if src in props and props[src] is not None:
                data[dst] = str(props[src])
        return data if data else None

    try:
        r = safe_exec("ioreg -rc IO80211Interface", timeout=8)
        if not r["success"] or not r["stdout"].strip():
            return None
        out = r["stdout"]
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
        return data if data else None
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
        if "maxspeed" in ext:
            parts.append(f"Max: {ext['maxspeed']} Mbps")
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
