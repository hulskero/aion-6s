import re
import shutil
from core.jailbreak import safe_exec


def _ifconfig_cell():
    """Basic cellular info from ifconfig pdp_ip0."""
    try:
        r = safe_exec("ifconfig pdp_ip0", timeout=8)
        if not r["success"] or not r["stdout"].strip():
            return {}
        out = r["stdout"]
        data = {}
        m = re.search(r'inet\s+(\S+)', out)
        data["ip"] = m.group(1) if m else "?"
        m = re.search(r'status:\s*(\S+)', out)
        data["status"] = m.group(1) if m else "?"
        return data
    except Exception:
        return {}


def _ioreg_cellular():
    """Extended cellular info via ioreg (requires IOKitTools)."""
    if not shutil.which("ioreg"):
        return None
    data = {}
    targets = [
        (["-rc", "AppleBaseband"], ["CarrierName", "Manufacturer", "FirmwareVersion", "imei"]),
        (["-rc", "CTBaseband"], ["CarrierName", "Manufacturer", "FirmwareVersion", "imei"]),
        (["-rc", "AppleARMPMUPowerStats"], []),
    ]
    for args, keys in targets:
        try:
            r = safe_exec("ioreg " + " ".join(args), timeout=8)
            if not r["success"] or not r["stdout"].strip():
                continue
            out = r["stdout"]
            def _get(k):
                m = re.search(rf'"{k}"\s*=\s*(\S+)', out)
                if m:
                    return m.group(1).rstrip(",")
                m = re.search(rf'"{k}"\s*=\s*"([^"]*)"', out)
                return m.group(1) if m else None
            for k in keys:
                v = _get(k)
                if v is not None:
                    data[k.lower()] = v
            m = re.search(r'signal|rssi', out, re.I)
            if m:
                sig = _get("rssi") or _get("RSSI") or _get("signal")
                if sig:
                    data["signal"] = sig
        except Exception:
            pass
    if not data:
        return None
    return data


def run_cellular(args=""):
    basic = _ifconfig_cell()
    ext = _ioreg_cellular()
    lines = ["Cellular:"]
    if ext:
        if "carriername" in ext:
            lines.append(f"  Carrier: {ext['carriername']}")
        if "signal" in ext:
            lines.append(f"  Signal: {ext['signal']} dBm")
        if "firmwareversion" in ext:
            lines.append(f"  Baseband FW: {ext['firmwareversion']}")
        for k, v in ext.items():
            if k not in ("carriername", "signal", "firmwareversion"):
                lines.append(f"  {k}: {v}")
    else:
        if shutil.which("ioreg"):
            lines.append("  Cellular info not found via ioreg")
        else:
            lines.append("  Install IOKitTools via Sileo for carrier/signal info")
    if basic:
        ip = basic.get("ip", "?")
        status = basic.get("status", "?")
        lines.append(f"  IP: {ip}  Status: {status}")
    else:
        lines.append("  pdp_ip0 not found (no cellular connection)")
    return "\n".join(lines)


SKILL = {
    "name": "cellular",
    "description": "Cellular info — carrier, signal, IP (needs IOKitTools for carrier/signal)",
    "run": run_cellular,
}
