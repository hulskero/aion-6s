import logging
import os
import re
import time
import ctypes
import shutil
from core.jailbreak import safe_exec

LOGGER = logging.getLogger(__name__)

_OBJC = None
_TTS_READY = None
_SEL_CACHE = {}
_CLS_CACHE = {}


def _load_objc():
    global _OBJC
    if _OBJC is not None:
        return _OBJC
    try:
        lib = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")

        get_class = lib.objc_getClass
        get_class.restype = ctypes.c_void_p
        get_class.argtypes = [ctypes.c_char_p]

        sel_reg = lib.sel_registerName
        sel_reg.restype = ctypes.c_void_p
        sel_reg.argtypes = [ctypes.c_char_p]

        CFN = ctypes.CFUNCTYPE

        m0 = CFN(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            ("objc_msgSend", lib)
        )

        m1 = CFN(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(("objc_msgSend", lib))

        mb = CFN(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
        )(("objc_msgSend", lib))

        libc = ctypes.cdll.LoadLibrary("libc.dylib")

        _OBJC = {
            "get_class": get_class,
            "sel_reg": sel_reg,
            "m0": m0,
            "m1": m1,
            "mb": mb,
            "libc": libc,
        }
        return _OBJC
    except Exception:
        _OBJC = False
        return None


def _cls(name):
    if name in _CLS_CACHE:
        return _CLS_CACHE[name]
    objc = _load_objc()
    if not objc:
        return None
    c = objc["get_class"](name.encode())
    _CLS_CACHE[name] = c
    return c


def _sel(name):
    if name in _SEL_CACHE:
        return _SEL_CACHE[name]
    objc = _load_objc()
    if not objc:
        return None
    s = objc["sel_reg"](name.encode())
    _SEL_CACHE[name] = s
    return s


def _cfstr(text):
    nsstr = _cls("NSString")
    if not nsstr:
        return None
    objc = _load_objc()
    return objc["m1"](nsstr, _sel("stringWithUTF8String:"), ctypes.c_char_p(text.encode()))


def _ensure_tts():
    global _TTS_READY
    if _TTS_READY is not None:
        return _TTS_READY
    try:
        dl = ctypes.cdll.LoadLibrary
        dl("/System/Library/Frameworks/AVFAudio.framework/AVFAudio")
        if _cls("AVSpeechSynthesizer"):
            _TTS_READY = True
            return True
        _TTS_READY = False
        return False
    except Exception:
        _TTS_READY = False
        return False


def _avail():
    return bool(_load_objc())


def _tts(text):
    if not _ensure_tts():
        return _tts_cli(text) if shutil.which("say") else "TTS unavailable (no AVFAudio or say)"
    objc = None
    pool = None
    synth = None
    try:
        objc = _load_objc()
        pool = objc["m0"](_cls("NSAutoreleasePool"), _sel("new"))

        av = _cls("AVSpeechSynthesizer")
        utt_cls = _cls("AVSpeechUtterance")
        voice_cls = _cls("AVSpeechSynthesisVoice")

        synth = objc["m0"](av, _sel("new"))

        text_ns = _cfstr(text)
        if not text_ns:
            return "TTS: failed to create NSString"

        utt = objc["m1"](utt_cls, _sel("speechUtteranceWithString:"), text_ns)
        if not utt:
            return "TTS: failed to create utterance"

        voice = objc["m1"](voice_cls, _sel("voiceWithLanguage:"), _cfstr("en-US"))
        if voice:
            objc["m1"](utt, _sel("setVoice:"), voice)

        objc["m1"](synth, _sel("speakUtterance:"), utt)

        deadline = time.time() + 30
        while time.time() < deadline:
            still = objc["m0"](synth, _sel("isSpeaking"))
            if not still:
                break
            time.sleep(0.3)

        return f"TTS: spoken \"{text[:100]}\""
    except Exception as e:
        return _tts_cli(text) if shutil.which("say") else f"TTS failed: {e}"
    finally:
        if synth and objc:
            objc["m0"](synth, _sel("release"))
        if pool and objc:
            objc["m0"](pool, _sel("drain"))


def _tts_cli(text):
    r = safe_exec(f"say '{text.replace(chr(39), chr(39)*2)}'", timeout=30)
    return "TTS: spoken" if r["success"] else f"TTS failed: {r['stderr'][:200]}"


def _ioreg_val(text, key):
    m = re.search(rf'"{key}"\s*=\s*"([^"]*)"', text)
    if m:
        return m.group(1)
    m = re.search(rf'"{key}"\s*=\s*(\S+)', text)
    return m.group(1).rstrip(",") if m else None


def _battery_info():
    r = safe_exec("ioreg -w 0 -rc AppleSmartBattery", timeout=8)
    if not r["success"] or not r["stdout"].strip():
        return None
    out = r["stdout"]
    data = {}
    for key in ("CurrentCapacity", "MaxCapacity", "DesignCapacity",
                 "CycleCount", "Temperature", "Voltage", "Amperage",
                 "IsCharging", "BatteryInstalled"):
        v = _ioreg_val(out, key)
        if v is not None:
            data[key] = v
    return data


def _battery():
    data = _battery_info()
    if not data:
        r = safe_exec("pmset -g batt", timeout=5)
        if r["success"]:
            return r["stdout"].strip()
        return "Battery info unavailable"
    try:
        cur = float(data.get("CurrentCapacity", 0))
        max_cap = float(data.get("MaxCapacity", 1))
        pct = round(cur / max_cap * 100) if max_cap else 0
    except (ValueError, ZeroDivisionError):
        pct = "?"
    is_ch = data.get("IsCharging", "").lower() == "yes"
    lines = [f"Battery: {pct}%, {'charging' if is_ch else 'discharging'}"]
    if "Temperature" in data:
        try:
            temp_k = float(data["Temperature"])
            temp_c = round(temp_k / 10 - 273.15, 1) if temp_k > 100 else round(temp_k, 1)
            lines.append(f"  Temp: {temp_c}C")
        except ValueError:
            pass
    for key, label in [("CycleCount", "Cycles"), ("Voltage", "mV"),
                        ("Amperage", "mA")]:
        if key in data:
            lines.append(f"  {label}: {data[key]}")
    return "\n".join(lines)


def _battery_health():
    data = _battery_info()
    if not data:
        return "Battery health unavailable"
    try:
        design = float(data.get("DesignCapacity", 1))
        max_cap = float(data.get("MaxCapacity", 1))
        pct = round(max_cap / design * 100) if design else 0
    except (ValueError, ZeroDivisionError):
        pct = "?"
    lines = [f"Battery Health: {pct}% of design capacity"]
    for key, label in [("DesignCapacity", "Design"), ("MaxCapacity", "Current Max"),
                        ("CycleCount", "Cycles")]:
        if key in data:
            lines.append(f"  {label}: {data[key]} mAh")
    if "Temperature" in data:
        try:
            temp_k = float(data["Temperature"])
            temp_c = round(temp_k / 10 - 273.15, 1) if temp_k > 100 else round(temp_k, 1)
            lines.append(f"  Temp: {temp_c}C")
        except ValueError:
            pass
    return "\n".join(lines)


def _cellular():
    basic = _ifconfig_pdp()
    ext = _ioreg_cellular()
    lines = []
    if ext:
        for key, label in [("CarrierName", "Carrier"), ("Manufacturer", "Mfr"),
                            ("FirmwareVersion", "FW")]:
            v = _ioreg_val(ext, key)
            if v:
                lines.append(f"  {label}: {v}")
        signal = _ioreg_val(ext, "rssi") or _ioreg_val(ext, "RSSI")
        if signal:
            lines.append(f"  Signal: {signal} dBm")
        for key in ("imei",):
            v = _ioreg_val(ext, key)
            if v:
                lines.append(f"  {key}: {v}")
    else:
        if shutil.which("ioreg"):
            lines.append("  Cellular: not found via ioreg")
        else:
            lines.append("  Cellular: install IOKitTools via Sileo")
    if basic:
        ip = basic.get("ip", "?")
        lines.append(f"  IP: {ip}")
    else:
        lines.append("  pdp_ip0: no cellular connection")
    return "\n".join(lines) if lines else "Cellular unavailable"


def _ifconfig_pdp():
    try:
        r = safe_exec("ifconfig pdp_ip0", timeout=5)
        if r["success"] and r["stdout"].strip():
            ip_m = re.search(r'inet\s+(\S+)', r["stdout"])
            return {"ip": ip_m.group(1) if ip_m else "?"}
    except Exception:
        LOGGER.debug("ifconfig pdp_ip0 failed")
    return {}


def _ioreg_cellular():
    for service in ("AppleBaseband", "CTBaseband"):
        r = safe_exec(f"ioreg -rc {service}", timeout=8)
        if r["success"] and r["stdout"].strip():
            return r["stdout"]
    return None


def _wifi():
    basic = _wifi_basic()
    ext = _wifi_ext()
    lines = []
    if ext:
        for key, label in [("SSID", "SSID"), ("BSSID", "BSSID"),
                            ("RSSI", "RSSI"), ("channel", "CH"),
                            ("noise", "Noise"), ("txRate", "TX")]:
            v = ext.get(key.lower())
            if v:
                lines.append(f"  {label}: {v}")
    else:
        lines.append("  Extended info: install IOKitTools via Sileo")
    if basic:
        for key, label in [("ip", "IP"), ("mac", "MAC"), ("status", "Status")]:
            v = basic.get(key)
            if v:
                lines.append(f"  {label}: {v}")
    return "\n".join(lines) if lines else "WiFi unavailable"


def _wifi_basic():
    try:
        r = safe_exec("ifconfig en0", timeout=5)
        if r["success"] and r["stdout"].strip():
            out = r["stdout"]
            data = {}
            m = re.search(r'inet\s+(\S+)', out)
            data["ip"] = m.group(1) if m else "?"
            m = re.search(r'ether\s+([0-9a-f:]+)', out)
            data["mac"] = m.group(1) if m else "?"
            m = re.search(r'status:\s*(\S+)', out)
            data["status"] = m.group(1) if m else "?"
            return data
    except Exception:
        LOGGER.debug("ifconfig en0 failed")
    return {}


def _wifi_ext():
    if not shutil.which("ioreg"):
        return None
    try:
        r = safe_exec("ioreg -rc IO80211Interface", timeout=8)
        if not r["success"] or not r["stdout"].strip():
            return None
        out = r["stdout"]
        data = {}
        ios_keys = {"SSID": "IO80211SSID", "BSSID": "IO80211BSSID"}
        for key in ("SSID", "BSSID", "RSSI", "channel", "noise", "txRate"):
            lookup = ios_keys.get(key, key)
            v = _ioreg_val(out, lookup) or _ioreg_val(out, key)
            if v is not None:
                data[key.lower()] = v
        return data if data else None
    except Exception:
        return None


def keep_awake(enabled=True):
    """Set iOS idleTimerDisabled — prevents sleep during streaming."""
    ui_app = _cls("UIApplication")
    if not ui_app:
        return False
    objc = _load_objc()
    if not objc:
        return False
    app = objc["m0"](ui_app, _sel("sharedApplication"))
    if not app:
        return False
    objc["mb"](app, _sel("setIdleTimerDisabled:"), enabled)
    return True


def _objc_test():
    objc = _load_objc()
    if not objc:
        return "ObjC runtime: NOT available"
    try:
        nsstr = _cls("NSString")
        test = objc["m1"](nsstr, _sel("stringWithUTF8String:"), ctypes.c_char_p(b"test"))
        if not test:
            return "ObjC runtime: available but NSString failed"
        tts = "yes" if _ensure_tts() else "no (loads AVFAudio, needs framework)"
        return f"ObjC runtime: OK  |  TTS ready: {tts}"
    except Exception as e:
        return f"ObjC runtime: FAILED ({e})"


HELP = """\
iOS System Bridge — system info + ObjC TTS.

Usage:
  @plugin ios_system                  — full status overview
  @plugin ios_system battery          — battery %% and stats
  @plugin ios_system battery --health — battery health vs design capacity
  @plugin ios_system cellular         — carrier, signal, IP
  @plugin ios_system wifi             — SSID, BSSID, RSSI, IP
  @plugin ios_system tts <text>       — speak text aloud (AVSpeechSynthesizer)
  @plugin ios_system objc-test        — test ObjC runtime availability
"""


def run_ios_system(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    subarg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd == "tts":
        if not subarg:
            return "Usage: @plugin ios_system tts <text>"
        return _tts(subarg)

    if subcmd == "battery":
        if subarg == "--health":
            return _battery_health()
        return _battery()

    if subcmd == "cellular":
        return _cellular()

    if subcmd == "wifi":
        return _wifi()

    if subcmd == "objc-test":
        return _objc_test()

    if subcmd == "status" or not subcmd:
        sections = []
        b = _battery()
        if b:
            sections.append(b)
        w = _wifi()
        if w:
            sections.append(w)
        c = _cellular()
        if c:
            sections.append(c)
        objc = _objc_test()
        sections.append(objc)
        return "\n\n".join(sections)

    return HELP


SKILL = {
    "name": "ios_system",
    "description": "iOS ObjC bridge — @plugin ios_system battery|cellular|wifi|tts|objc-test",
    "run": run_ios_system,
}
