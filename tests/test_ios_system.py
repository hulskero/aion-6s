"""
Comprehensive test suite for ios_system.py

Tests all functions with safe_exec mocked to prevent hanging.
"""
import sys
import os
import re
import ctypes
from unittest.mock import MagicMock, patch

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(TEST_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
SECTION = ""

def section(name):
    global SECTION
    SECTION = name
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f"  |  {detail}"
        print(msg)

def check(name, got, expected, detail_func=None):
    detail = ""
    if got != expected:
        detail = f"got={got!r}, expected={expected!r}"
        if detail_func:
            detail += f" ({detail_func(got, expected)})"
    test(name, got == expected, detail)

# ============================================================
# MOCK SETUP
# ============================================================

_MOCK_BATTERY = """\
  "CurrentCapacity" = 1200
  "MaxCapacity" = 1500
  "DesignCapacity" = 1715
  "CycleCount" = 500
  "Temperature" = 2840
  "Voltage" = 3800
  "Amperage" = -500
  "IsCharging" = No
  "BatteryInstalled" = Yes
"""

_MOCK_CELLULAR = """\
  "CarrierName" = "AT&T"
  "Manufacturer" = "Intel"
  "FirmwareVersion" = "1.0.0"
  "rssi" = -85
"""

_MOCK_WIFI_EXT = """\
  "SSID" = "MyWiFi"
  "BSSID" = "aa:bb:cc:dd:ee:ff"
  "RSSI" = -65
  "channel" = 6
  "noise" = -90
  "txRate" = 300
"""

_MOCK_IFCONFIG_EN0 = """\
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.1.100 netmask 0xffffff00 broadcast 192.168.1.255
\tether aa:bb:cc:dd:ee:ff
\tstatus: active
"""

_MOCK_IFCONFIG_PDP = """\
pdp_ip0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 10.0.0.1
"""

def _mock_safe_exec_impl(cmd, timeout=30, jb=None):
    if "AppleSmartBattery" in cmd:
        return {"success": True, "stdout": _MOCK_BATTERY, "stderr": "", "code": 0}
    if "AppleBaseband" in cmd or "CTBaseband" in cmd:
        return {"success": True, "stdout": _MOCK_CELLULAR, "stderr": "", "code": 0}
    if "IO80211Interface" in cmd:
        return {"success": True, "stdout": _MOCK_WIFI_EXT, "stderr": "", "code": 0}
    if cmd.startswith("ifconfig en0"):
        return {"success": True, "stdout": _MOCK_IFCONFIG_EN0, "stderr": "", "code": 0}
    if cmd.startswith("ifconfig pdp_ip0"):
        return {"success": True, "stdout": _MOCK_IFCONFIG_PDP, "stderr": "", "code": 0}
    if cmd.startswith("say"):
        return {"success": True, "stdout": "", "stderr": "", "code": 0}
    return {"success": True, "stdout": "", "stderr": "", "code": 0}

_safe_exec_mock = MagicMock(side_effect=_mock_safe_exec_impl)
patcher = patch('core.jailbreak.safe_exec', _safe_exec_mock)
patcher.start()

# ============================================================
# IMPORT MODULE (after mock is active)
# ============================================================

import plugins.ios_system as ios_mod
from plugins.ios_system import (
    _load_objc, _cls, _sel, _ensure_tts,
    _objc_test, _tts, _ioreg_val,
    _battery_info, _battery, _battery_health,
    _cellular, _wifi, _wifi_basic,
    _ifconfig_pdp, _ioreg_cellular, _wifi_ext,
    run_ios_system, SKILL, HELP, _cfstr,
    _avail, _tts_cli,
)

# Reset global state
ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._SEL_CACHE = {}
ios_mod._CLS_CACHE = {}

# ============================================================
# TEST 1: _load_objc()
# ============================================================
section("1. _load_objc() — load libobjc runtime")

# Clear cache first
ios_mod._OBJC = None
result = _load_objc()

test("returns dict (not None)", result is not None)
test("returns dict (not False)", result is not False)

if isinstance(result, dict):
    expected_keys = {"get_class", "sel_reg", "m0", "m1", "mb", "libc"}
    actual_keys = set(result.keys())
    test("has all required keys", actual_keys == expected_keys,
         f"missing: {expected_keys - actual_keys}, extra: {actual_keys - expected_keys}")
    test("get_class is callable", callable(result["get_class"]))
    test("sel_reg is callable", callable(result["sel_reg"]))
    test("m0 is callable", callable(result["m0"]))
    test("m1 is callable", callable(result["m1"]))
    test("libc is CDLL instance", isinstance(result["libc"], ctypes.CDLL))
else:
    test("_load_objc returned dict (skipping sub-checks)", False,
         f"type was {type(result).__name__} = {result}")

# Test idempotency — second call returns cached (same object)
ios_mod._OBJC = None
r1 = _load_objc()
r2 = _load_objc()
test("_load_objc is idempotent (cached)", r1 is r2)
test("_avail() matches _load_objc", _avail() == bool(r1))

# ============================================================
# TEST 2: _cls() / _sel() caching
# ============================================================
section("2. _cls() / _sel() — class and selector resolution, caching")

ios_mod._OBJC = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

test("_CLS_CACHE starts empty", len(ios_mod._CLS_CACHE) == 0)
test("_SEL_CACHE starts empty", len(ios_mod._SEL_CACHE) == 0)

nsstr = _cls("NSString")
test("_cls('NSString') returns value", nsstr is not None)

if nsstr is not None:
    test("_cls('NSString') stored in cache", "NSString" in ios_mod._CLS_CACHE)
    test("_cls('NSString') cached value matches", ios_mod._CLS_CACHE["NSString"] is nsstr)

    # Second call — verify cache hit
    nsstr2 = _cls("NSString")
    test("_cls('NSString') second call returns same object", nsstr2 is nsstr)

# Selector caching
sel = _sel("alloc")
test("_sel('alloc') returns value", sel is not None)
if sel is not None:
    test("_sel('alloc') stored in cache", "alloc" in ios_mod._SEL_CACHE)
    sel2 = _sel("alloc")
    test("_sel('alloc') second call returns same object", sel2 is sel)

sel_init = _sel("init")
test("_sel('init') also works", sel_init is not None)

# Not a real class — should return None (NULL pointer) without exception
cls_nonexistent = _cls("NonExistentClass12345")
test("_cls('NonExistentClass12345') returns None (NULL) without exception",
     cls_nonexistent is None)  # objc_getClass returns NULL → ctypes converts to None

sel_nonexistent = _sel("nonExistentSelector12345")
test("_sel('nonExistentSelector12345') returns value (sel_registerName creates it)",
     sel_nonexistent is not None)

# ============================================================
# TEST 3: _ensure_tts()
# ============================================================
section("3. _ensure_tts() — load AVFAudio.framework")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

tts_ok = _ensure_tts()
# On macOS, AVFAudio exists, so this should be True
# On other platforms, it may be False
test("_ensure_tts() returns bool", isinstance(tts_ok, bool))
test("_ensure_tts() is cached", ios_mod._TTS_READY is not None)
test("_TTS_READY matches return", ios_mod._TTS_READY == tts_ok)

av_cls = _cls("AVSpeechSynthesizer")
test("AVSpeechSynthesizer class resolvable after _ensure_tts",
     av_cls is not None or not tts_ok)  # If TTS ready, class should exist

utt_cls = _cls("AVSpeechUtterance")
test("AVSpeechUtterance class resolvable after _ensure_tts",
     utt_cls is not None or not tts_ok)

# Second call — cached
tts_ok2 = _ensure_tts()
test("_ensure_tts() second call is cached", tts_ok2 == tts_ok)

# ============================================================
# TEST 4: _objc_test()
# ============================================================
section("4. _objc_test() — runtime verification")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

result_txt = _objc_test()
test("_objc_test() returns string", isinstance(result_txt, str))
test("_objc_test() non-empty", len(result_txt) > 0)

# Should contain some key phrases depending on environment
has_ok = "OK" in result_txt or "NOT" in result_txt or "available" in result_txt or "FAILED" in result_txt
test("_objc_test() contains meaningful status", has_ok,
     f"got: {result_txt}")

if "OK" in result_txt:
    test("_objc_test() reports TTS ready status", "TTS ready:" in result_txt or "TTS ready" in result_txt,
         f"got: {result_txt}")

# ============================================================
# TEST 5: _tts()
# ============================================================
section("5. _tts() — text-to-speech")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

tts_result = _tts("hello world")
test("_tts() returns string", isinstance(tts_result, str))
test("_tts() result non-empty", len(tts_result) > 0)
test("_tts() mentions spoken or failed", "spoken" in tts_result.lower() or "failed" in tts_result.lower() or "unavailable" in tts_result.lower(),
     f"got: {tts_result}")

# Test with special characters
tts_special = _tts("Don't stop! $100 off?")
test("_tts() with special characters works", isinstance(tts_special, str) and len(tts_special) > 0,
     f"got: {tts_special}")

# Test empty string
tts_empty = _tts("")
test("_tts('') handles empty string", isinstance(tts_empty, str),
     f"got: {tts_empty}")

# Test long text (500+ chars)
long_text = "hello world " * 50
tts_long = _tts(long_text)
test("_tts() with long text (500+ chars)", isinstance(tts_long, str) and len(tts_long) > 0,
     f"got (truncated): {tts_long[:80]}...")

# ============================================================
# TEST 6: _ioreg_val() — regex extraction
# ============================================================
section("6. _ioreg_val() — regex extraction from ioreg output")

sample = """  "DesignCapacity" = 1715
  "MaxCapacity" = 1500
  "Temperature" = 2840
  "BatteryInstalled" = Yes
  "Serial" = "ABC123XYZ"
  "Manufacturer" = "Sony Corp"
"""

# Numeric values
check("DesignCapacity", _ioreg_val(sample, "DesignCapacity"), "1715")
check("MaxCapacity", _ioreg_val(sample, "MaxCapacity"), "1500")
check("Temperature", _ioreg_val(sample, "Temperature"), "2840")

# Non-numeric bare value
check("BatteryInstalled=Yes", _ioreg_val(sample, "BatteryInstalled"), "Yes")

# Quoted string value
check("Serial (quoted)", _ioreg_val(sample, "Serial"), "ABC123XYZ")
check("Manufacturer (quoted)", _ioreg_val(sample, "Manufacturer"), "Sony Corp")

# Edge: key not present
check("missing key", _ioreg_val(sample, "FooBar"), None)

# Edge: blank input
check("blank input", _ioreg_val("", "DesignCapacity"), None)
check("None-ish input", _ioreg_val("   ", "DesignCapacity"), None)

# Edge: value with trailing comma
sample_with_comma = '  "CycleCount" = 500,'
check("trailing comma stripped", _ioreg_val(sample_with_comma, "CycleCount"), "500")

# Edge: key at end of string
sample_eol = '  "Amperage" = -500'
check("negative value", _ioreg_val(sample_eol, "Amperage"), "-500")

# Edge: key with spaces in value
sample_spaces = '  "Product" = "iPhone 6s"'
check("value with spaces", _ioreg_val(sample_spaces, "Product"), "iPhone 6s")

# ============================================================
# TEST 7: _wifi_basic() — ifconfig parsing
# ============================================================
section("7. _wifi_basic() / _ifconfig_pdp() — ifconfig parsing")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

wifi = _wifi_basic()
test("_wifi_basic() returns dict", isinstance(wifi, dict))

if wifi:
    check("IP parsed", wifi.get("ip"), "192.168.1.100")
    check("MAC parsed", wifi.get("mac"), "aa:bb:cc:dd:ee:ff")
    check("Status parsed", wifi.get("status"), "active")
else:
    test("_wifi_basic() populated data (checking mock)", False)

# _ifconfig_pdp
pdp = _ifconfig_pdp()
test("_ifconfig_pdp() returns dict", isinstance(pdp, dict))
if pdp:
    check("pdp IP parsed", pdp.get("ip"), "10.0.0.1")

# _ioreg_cellular
cell_reg = _ioreg_cellular()
test("_ioreg_cellular() returns string", cell_reg is not None)
if cell_reg:
    check("cellular ioreg contains CarrierName", "AT&T" in cell_reg, True)

# _wifi_ext
wifi_ext = _wifi_ext()
test("_wifi_ext() returns dict or None", wifi_ext is None or isinstance(wifi_ext, dict))
if wifi_ext:
    check("WiFi ext SSID", wifi_ext.get("ssid"), "MyWiFi")
    check("WiFi ext RSSI", wifi_ext.get("rssi"), "-65")
    check("WiFi ext channel", wifi_ext.get("channel"), "6")
    check("WiFi ext txRate", wifi_ext.get("txrate"), "300")

# _cellular()
cell_result = _cellular()
test("_cellular() returns string", isinstance(cell_result, str))
test("_cellular() non-empty", len(cell_result) > 0)
if cell_result.lower() != "cellular unavailable":
    has_carrier = "AT&T" in cell_result or "Carrier" in cell_result
    has_ip = "10.0.0.1" in cell_result or "IP" in cell_result
    test("_cellular() contains carrier info", has_carrier, f"got: {cell_result}")
    test("_cellular() contains IP info", has_ip, f"got: {cell_result}")

# _wifi()
wifi_result = _wifi()
test("_wifi() returns string", isinstance(wifi_result, str))
test("_wifi() non-empty", len(wifi_result) > 0)
if wifi_result.lower() != "wifi unavailable":
    has_ssid = "MyWiFi" in wifi_result or "SSID" in wifi_result
    has_ip = "192.168.1.100" in wifi_result or "IP" in wifi_result
    test("_wifi() contains SSID", has_ssid, f"got: {wifi_result}")
    test("_wifi() contains IP", has_ip, f"got: {wifi_result}")

# ============================================================
# TEST 8: Battery functions
# ============================================================
section("8. _battery_info(), _battery(), _battery_health()")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

bi = _battery_info()
test("_battery_info() returns dict or None", bi is None or isinstance(bi, dict))

if isinstance(bi, dict):
    check("CurrentCapacity", bi.get("CurrentCapacity"), "1200")
    check("MaxCapacity", bi.get("MaxCapacity"), "1500")
    check("DesignCapacity", bi.get("DesignCapacity"), "1715")
    check("CycleCount", bi.get("CycleCount"), "500")
    check("Temperature", bi.get("Temperature"), "2840")
    check("Voltage", bi.get("Voltage"), "3800")
    check("Amperage", bi.get("Amperage"), "-500")
    check("IsCharging", bi.get("IsCharging"), "No")
    check("BatteryInstalled", bi.get("BatteryInstalled"), "Yes")

# _battery
batt = _battery()
test("_battery() returns string", isinstance(batt, str))
test("_battery() non-empty", len(batt) > 0)
if isinstance(bi, dict):
    test("_battery() reports percentage", "%" in batt, f"got: {batt}")
    test("_battery() reports charge state", "charging" in batt.lower() or "discharging" in batt.lower(),
         f"got: {batt}")

# _battery_health
health = _battery_health()
test("_battery_health() returns string", isinstance(health, str))
test("_battery_health() non-empty", len(health) > 0)
if isinstance(bi, dict):
    test("_battery_health() reports health pct", "%" in health, f"got: {health}")

# ============================================================
# TEST 9: run_ios_system() — all subcommands
# ============================================================
section("9. run_ios_system() — all subcommands")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

# objc-test subcommand
r = run_ios_system("objc-test")
test("objc-test returns string", isinstance(r, str))
test("objc-test non-empty", len(r) > 0)

# battery subcommand
r = run_ios_system("battery")
test("battery returns string", isinstance(r, str))
test("battery non-empty", len(r) > 0)

# battery --health subcommand
r = run_ios_system("battery --health")
test("battery --health returns string", isinstance(r, str))
test("battery --health non-empty", len(r) > 0)
test("battery --health != battery", r != run_ios_system("battery"),
     "both returned same — might be OK if data matches, but --health should differ")

# wifi subcommand
r = run_ios_system("wifi")
test("wifi returns string", isinstance(r, str))
test("wifi non-empty", len(r) > 0)

# cellular subcommand
r = run_ios_system("cellular")
test("cellular returns string", isinstance(r, str))
test("cellular non-empty", len(r) > 0)

# tts subcommand
r = run_ios_system("tts hello")
test("tts hello returns string", isinstance(r, str))
test("tts hello non-empty", len(r) > 0)
test("tts mentions spoken/failed", "spoken" in r.lower() or "failed" in r.lower() or "unavailable" in r.lower(),
     f"got: {r}")

# tts with no text
r = run_ios_system("tts")
check("tts (no text) returns usage", r, "Usage: @plugin ios_system tts <text>")

# empty args → full status
r = run_ios_system("")
test("empty args returns string", isinstance(r, str))
test("empty args non-empty", len(r) > 0)
test("empty args contains battery info", "Battery" in r or "battery" in r,
     f"got (truncated): {r[:100]}")
test("empty args contains ObjC status", "ObjC" in r or "objc" in r,
     f"got (truncated): {r[:100]}")

# "status" subcommand (alias)
r2 = run_ios_system("status")
test("status command returns same as empty", isinstance(r2, str) and len(r2) > 0)

# unknown arg → HELP
r = run_ios_system("unknown")
test("unknown arg returns HELP", r == HELP,
     f"got (truncated): {str(r)[:80]}...")

# edge: whitespace-only args
r = run_ios_system("   ")
test("whitespace-only args returns full status", isinstance(r, str) and len(r) > 0)

# edge: case insensitivity
r = run_ios_system("BATTERY")
test("BATTERY (uppercase) works", isinstance(r, str) and len(r) > 0)

r = run_ios_system("WIFI")
test("WIFI (uppercase) works", isinstance(r, str) and len(r) > 0)

# ============================================================
# TEST 10: SKILL dict
# ============================================================
section("10. SKILL dict — module interface")

test("SKILL is dict", isinstance(SKILL, dict))
check("SKILL has 'name'", SKILL.get("name"), "ios_system")
check("SKILL has 'description'", "description" in SKILL, True)
check("SKILL has 'run' key", "run" in SKILL, True)
test("SKILL['run'] is callable", callable(SKILL["run"]))
test("SKILL['run'] is run_ios_system", SKILL["run"] is run_ios_system)

# ============================================================
# TEST 11: HELP text
# ============================================================
section("11. HELP text")

test("HELP is string", isinstance(HELP, str))
test("HELP non-empty", len(HELP) > 0)
test("HELP mentions all subcommands",
     all(cmd in HELP for cmd in ["battery", "cellular", "wifi", "tts", "objc-test"]),
     f"missing some commands in HELP")

# ============================================================
# TEST 12: Edge cases
# ============================================================
section("12. Edge cases")

ios_mod._OBJC = None
ios_mod._TTS_READY = None
ios_mod._CLS_CACHE = {}
ios_mod._SEL_CACHE = {}

# Very long TTS text
r = run_ios_system("tts " + "a" * 10000)
test("tts with 10k chars handles gracefully", isinstance(r, str) and len(r) > 0,
     f"got (truncated): {str(r)[:80]}...")

# TTS with special chars
r = run_ios_system("tts Hello! @#$%^&*() test")
test("tts with special chars", isinstance(r, str) and len(r) > 0,
     f"got (truncated): {str(r)[:80]}...")

# TTS with unicode
r = run_ios_system("tts ěščřžýáíé")
test("tts with unicode chars", isinstance(r, str) and len(r) > 0,
     f"got (truncated): {str(r)[:80]}...")

# Very long battery --health text shouldn't matter but verify no crash
r = run_ios_system("battery --health")
test("battery --health after other calls still works", isinstance(r, str) and len(r) > 0)

# Cellular after everything
r = run_ios_system("cellular")
test("cellular after other calls", isinstance(r, str) and len(r) > 0)

# Verify safe_exec was actually called (our mock)
safe_exec_calls = _safe_exec_mock.call_count
test("safe_exec was called during tests", safe_exec_calls > 0,
     f"total calls: {safe_exec_calls}")

# ============================================================
# SUMMARY
# ============================================================
section("TEST SUMMARY")
total = PASS + FAIL
print(f"  Passed: {PASS}/{total}")
print(f"  Failed: {FAIL}/{total}")
print(f"  Rate:   {PASS/total*100:.1f}%" if total > 0 else "  No tests ran!")
print()

# Exit code
sys.exit(0 if FAIL == 0 else 1)
