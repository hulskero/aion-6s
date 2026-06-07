import re
import shutil
from core.jailbreak import safe_exec
from core.ios_hw import ioreg_get_first


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


def _plist_carrier():
    try:
        import plistlib
        path = '/var/mobile/Library/Preferences/com.apple.CommCenter.plist'
        with open(path, 'rb') as f:
            d = plistlib.load(f)
        carrier = d.get('CarrierName') or d.get('carrier') or d.get('currentCarrier')
        if carrier:
            return str(carrier)
    except Exception:
        pass
    try:
        import plistlib, glob
        bundles = glob.glob('/System/Library/Carrier Bundles/*/carrier.plist')
        for path in bundles[:3]:
            with open(path, 'rb') as f:
                d = plistlib.load(f)
            name = d.get('CarrierName')
            if name:
                return str(name)
    except Exception:
        pass
    return None


def _ioreg_cellular_ctypes():
    data = {}
    for name in ("AppleBaseband", "AppleBasebandPCI"):
        props = ioreg_get_first(name)
        if props:
            mapping = {
                "CarrierName": "carrier",
                "Manufacturer": "manufacturer",
                "FirmwareVersion": "firmware",
                "IMEI": "imei",
            }
            for iokey, datakey in mapping.items():
                v = props.get(iokey)
                if v is not None:
                    data[datakey] = str(v)
            for sigkey in ("RSSI", "SignalStrength"):
                v = props.get(sigkey)
                if v is not None:
                    data["signal"] = str(v)
                    break
            if data:
                break
    return data if data else None


def _ioreg_cellular_shell():
    if not shutil.which("ioreg"):
        return None
    data = {}
    targets = [
        (["-rc", "AppleBaseband"], ["CarrierName", "Manufacturer", "FirmwareVersion", "imei"]),
        (["-rc", "AppleBasebandPCI"], ["CarrierName", "Manufacturer", "FirmwareVersion", "imei"]),
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
            sig = _get("RSSI") or _get("SignalStrength")
            if sig:
                data["signal"] = sig
        except Exception:
            pass
    return data if data else None


def run_cellular(args=""):
    basic = _ifconfig_cell()
    ext = _ioreg_cellular_ctypes()
    if not ext:
        ext = _ioreg_cellular_shell()
    lines = ["Cellular:"]
    if ext:
        carrier = ext.get("carrier") or ext.get("carriername")
        if not carrier:
            carrier = _plist_carrier()
        if carrier:
            lines.append(f"  Carrier: {carrier}")
        sig = ext.get("signal")
        if sig:
            lines.append(f"  Signal: {sig} dBm")
        fw = ext.get("firmware") or ext.get("firmwareversion")
        if fw:
            lines.append(f"  Baseband FW: {fw}")
        for k, v in ext.items():
            if k not in ("carrier", "carriername", "signal", "firmware", "firmwareversion"):
                lines.append(f"  {k}: {v}")
    else:
        carrier = _plist_carrier()
        if carrier:
            lines.append(f"  Carrier: {carrier}")
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
