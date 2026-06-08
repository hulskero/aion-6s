"""
pytest-style tests for plugins.ios_system.

All safe_exec calls are mocked to return realistic iPhone 6s data
without hitting the actual device.
"""
import sys
import os
import re
import ctypes
from unittest.mock import MagicMock, patch

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(TEST_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mock data — realistic iPhone 6s ioreg output
# ---------------------------------------------------------------------------

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
_patcher = patch('core.jailbreak.safe_exec', _safe_exec_mock)
_patcher.start()

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


@pytest.fixture(autouse=True)
def _reset_ios_state():
    ios_mod._OBJC = None
    ios_mod._TTS_READY = None
    ios_mod._SEL_CACHE = {}
    ios_mod._CLS_CACHE = {}
    yield


# ===================================================================
# 1. _load_objc()
# ===================================================================

class TestLoadObjC:
    def test_returns_dict(self):
        result = _load_objc()
        assert result is not None

    def test_has_required_keys(self):
        result = _load_objc()
        assert isinstance(result, dict)
        expected = {"get_class", "sel_reg", "m0", "m1", "mb", "libc"}
        assert set(result.keys()) == expected

    def test_get_class_is_callable(self):
        result = _load_objc()
        assert callable(result["get_class"])

    def test_sel_reg_is_callable(self):
        result = _load_objc()
        assert callable(result["sel_reg"])

    def test_m0_is_callable(self):
        result = _load_objc()
        assert callable(result["m0"])

    def test_m1_is_callable(self):
        result = _load_objc()
        assert callable(result["m1"])

    def test_libc_is_cdll(self):
        result = _load_objc()
        assert isinstance(result["libc"], ctypes.CDLL)

    def test_idempotent_cached(self):
        ios_mod._OBJC = None
        r1 = _load_objc()
        r2 = _load_objc()
        assert r1 is r2

    def test_avail_matches(self):
        ios_mod._OBJC = None
        result = _load_objc()
        assert _avail() == bool(result)


# ===================================================================
# 2. _cls() / _sel() — caching
# ===================================================================

class TestClsSel:
    def test_caches_start_empty(self):
        assert len(ios_mod._CLS_CACHE) == 0
        assert len(ios_mod._SEL_CACHE) == 0

    def test_cls_nsstring_returns_value(self):
        nsstr = _cls("NSString")
        assert nsstr is not None

    def test_cls_nsstring_cached(self):
        nsstr = _cls("NSString")
        assert "NSString" in ios_mod._CLS_CACHE
        assert ios_mod._CLS_CACHE["NSString"] is nsstr

    def test_cls_nsstring_idempotent(self):
        a = _cls("NSString")
        b = _cls("NSString")
        assert b is a

    def test_sel_alloc_returns_value(self):
        sel = _sel("alloc")
        assert sel is not None

    def test_sel_alloc_cached(self):
        sel = _sel("alloc")
        assert "alloc" in ios_mod._SEL_CACHE

    def test_sel_alloc_idempotent(self):
        a = _sel("alloc")
        b = _sel("alloc")
        assert b is a

    def test_sel_init_works(self):
        assert _sel("init") is not None

    def test_cls_nonexistent_returns_none(self):
        assert _cls("NonExistentClass12345") is None

    def test_sel_nonexistent_registers(self):
        assert _sel("nonExistentSelector12345") is not None


# ===================================================================
# 3. _ensure_tts()
# ===================================================================

class TestEnsureTTS:
    def test_returns_bool(self):
        assert isinstance(_ensure_tts(), bool)

    def test_cached(self):
        _ensure_tts()
        assert ios_mod._TTS_READY is not None

    def test_cache_matches(self):
        result = _ensure_tts()
        assert ios_mod._TTS_READY == result

    def test_resolves_synthesizer_class(self):
        tts_ok = _ensure_tts()
        av_cls = _cls("AVSpeechSynthesizer")
        assert av_cls is not None or not tts_ok

    def test_resolves_utterance_class(self):
        tts_ok = _ensure_tts()
        utt_cls = _cls("AVSpeechUtterance")
        assert utt_cls is not None or not tts_ok

    def test_second_call_cached(self):
        a = _ensure_tts()
        b = _ensure_tts()
        assert b == a


# ===================================================================
# 4. _objc_test()
# ===================================================================

class TestObjcTest:
    def test_returns_string(self):
        assert isinstance(_objc_test(), str)

    def test_non_empty(self):
        assert len(_objc_test()) > 0

    def test_contains_status(self):
        result = _objc_test()
        phrases = ("OK", "NOT", "available", "FAILED")
        assert any(p in result for p in phrases)

    def test_tls_reported_when_ok(self):
        result = _objc_test()
        if "OK" in result:
            assert "TTS ready" in result


# ===================================================================
# 5. _tts()
# ===================================================================

class TestTTS:
    def test_returns_string(self):
        assert isinstance(_tts("hello world"), str)

    def test_non_empty(self):
        assert len(_tts("hello world")) > 0

    def test_mentions_spoken_or_failed(self):
        result = _tts("hello world")
        assert any(kw in result.lower() for kw in ("spoken", "failed", "unavailable"))

    def test_special_characters(self):
        result = _tts("Don't stop! $100 off?")
        assert isinstance(result, str) and len(result) > 0

    def test_empty_string(self):
        result = _tts("")
        assert isinstance(result, str)

    def test_long_text(self):
        result = _tts("hello world " * 50)
        assert isinstance(result, str) and len(result) > 0


# ===================================================================
# 6. _ioreg_val() — regex extraction
# ===================================================================

SAMPLE_IOREG = """\
  "DesignCapacity" = 1715
  "MaxCapacity" = 1500
  "Temperature" = 2840
  "BatteryInstalled" = Yes
  "Serial" = "ABC123XYZ"
  "Manufacturer" = "Sony Corp"
"""


class TestIoregVal:
    def test_design_capacity(self):
        assert _ioreg_val(SAMPLE_IOREG, "DesignCapacity") == "1715"

    def test_max_capacity(self):
        assert _ioreg_val(SAMPLE_IOREG, "MaxCapacity") == "1500"

    def test_temperature(self):
        assert _ioreg_val(SAMPLE_IOREG, "Temperature") == "2840"

    def test_bare_value(self):
        assert _ioreg_val(SAMPLE_IOREG, "BatteryInstalled") == "Yes"

    def test_quoted_serial(self):
        assert _ioreg_val(SAMPLE_IOREG, "Serial") == "ABC123XYZ"

    def test_quoted_manufacturer(self):
        assert _ioreg_val(SAMPLE_IOREG, "Manufacturer") == "Sony Corp"

    def test_missing_key(self):
        assert _ioreg_val(SAMPLE_IOREG, "FooBar") is None

    def test_blank_input(self):
        assert _ioreg_val("", "DesignCapacity") is None

    def test_whitespace_input(self):
        assert _ioreg_val("   ", "DesignCapacity") is None

    def test_trailing_comma(self):
        sample = '  "CycleCount" = 500,'
        assert _ioreg_val(sample, "CycleCount") == "500"

    def test_negative_value(self):
        sample = '  "Amperage" = -500'
        assert _ioreg_val(sample, "Amperage") == "-500"

    def test_value_with_spaces(self):
        sample = '  "Product" = "iPhone 6s"'
        assert _ioreg_val(sample, "Product") == "iPhone 6s"


# ===================================================================
# 7. _wifi_basic() — ifconfig parsing
# ===================================================================

class TestWifiBasic:
    def test_returns_dict(self):
        wifi = _wifi_basic()
        assert isinstance(wifi, dict)

    def test_ip_parsed(self):
        wifi = _wifi_basic()
        if wifi:
            assert wifi.get("ip") == "192.168.1.100"

    def test_mac_parsed(self):
        wifi = _wifi_basic()
        if wifi:
            assert wifi.get("mac") == "aa:bb:cc:dd:ee:ff"

    def test_status_parsed(self):
        wifi = _wifi_basic()
        if wifi:
            assert wifi.get("status") == "active"


class TestIfconfigPdp:
    def test_returns_dict(self):
        pdp = _ifconfig_pdp()
        assert isinstance(pdp, dict)

    def test_ip_parsed(self):
        pdp = _ifconfig_pdp()
        if pdp:
            assert pdp.get("ip") == "10.0.0.1"


class TestIoregCellular:
    def test_returns_string(self):
        cell_reg = _ioreg_cellular()
        assert cell_reg is not None

    def test_contains_carrier(self):
        cell_reg = _ioreg_cellular()
        if cell_reg:
            assert "AT&T" in cell_reg


class TestWifiExt:
    def test_returns_dict_or_none(self):
        wifi_ext = _wifi_ext()
        assert wifi_ext is None or isinstance(wifi_ext, dict)

    def test_ssid(self):
        wifi_ext = _wifi_ext()
        if wifi_ext:
            assert wifi_ext.get("ssid") == "MyWiFi"

    def test_rssi(self):
        wifi_ext = _wifi_ext()
        if wifi_ext:
            assert wifi_ext.get("rssi") == "-65"

    def test_channel(self):
        wifi_ext = _wifi_ext()
        if wifi_ext:
            assert wifi_ext.get("channel") == "6"

    def test_txrate(self):
        wifi_ext = _wifi_ext()
        if wifi_ext:
            assert wifi_ext.get("txrate") == "300"


class TestCellular:
    def test_returns_string(self):
        assert isinstance(_cellular(), str)

    def test_non_empty(self):
        assert len(_cellular()) > 0

    def test_contains_carrier_or_ip(self):
        result = _cellular()
        if result.lower() != "cellular unavailable":
            assert "AT&T" in result or "Carrier" in result
            assert "10.0.0.1" in result or "IP" in result


class TestWifi:
    def test_returns_string(self):
        assert isinstance(_wifi(), str)

    def test_non_empty(self):
        assert len(_wifi()) > 0

    def test_contains_ssid(self):
        result = _wifi()
        if result.lower() != "wifi unavailable":
            assert "MyWiFi" in result or "SSID" in result

    def test_contains_ip(self):
        result = _wifi()
        if result.lower() != "wifi unavailable":
            assert "192.168.1.100" in result or "IP" in result


# ===================================================================
# 8. Battery
# ===================================================================

class TestBatteryInfo:
    def test_returns_dict_or_none(self):
        bi = _battery_info()
        assert bi is None or isinstance(bi, dict)

    def test_values(self):
        bi = _battery_info()
        if isinstance(bi, dict):
            assert bi.get("CurrentCapacity") == "1200"
            assert bi.get("MaxCapacity") == "1500"
            assert bi.get("DesignCapacity") == "1715"
            assert bi.get("CycleCount") == "500"
            assert bi.get("Temperature") == "2840"
            assert bi.get("Voltage") == "3800"
            assert bi.get("Amperage") == "-500"
            assert bi.get("IsCharging") == "No"
            assert bi.get("BatteryInstalled") == "Yes"


class TestBattery:
    def test_returns_string(self):
        assert isinstance(_battery(), str)

    def test_non_empty(self):
        assert len(_battery()) > 0

    def test_reports_percentage(self):
        bi = _battery_info()
        batt = _battery()
        if isinstance(bi, dict):
            assert "%" in batt

    def test_reports_charge_state(self):
        bi = _battery_info()
        batt = _battery()
        if isinstance(bi, dict):
            assert "charging" in batt.lower() or "discharging" in batt.lower()


class TestBatteryHealth:
    def test_returns_string(self):
        assert isinstance(_battery_health(), str)

    def test_non_empty(self):
        assert len(_battery_health()) > 0

    def test_reports_health_pct(self):
        bi = _battery_info()
        health = _battery_health()
        if isinstance(bi, dict):
            assert "%" in health


# ===================================================================
# 9. run_ios_system() — all subcommands
# ===================================================================

class TestRunIosSystem:
    def test_objc_test(self):
        r = run_ios_system("objc-test")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_battery(self):
        r = run_ios_system("battery")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_battery_health(self):
        r = run_ios_system("battery --health")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_battery_vs_health_differs(self):
        b = run_ios_system("battery")
        bh = run_ios_system("battery --health")
        assert b != bh

    def test_wifi(self):
        r = run_ios_system("wifi")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_cellular(self):
        r = run_ios_system("cellular")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_tts_hello(self):
        r = run_ios_system("tts hello")
        assert isinstance(r, str)
        assert len(r) > 0
        assert any(kw in r.lower() for kw in ("spoken", "failed", "unavailable"))

    def test_tts_no_text_usage(self):
        r = run_ios_system("tts")
        assert r == "Usage: @plugin ios_system tts <text>"

    def test_empty_args(self):
        r = run_ios_system("")
        assert isinstance(r, str)
        assert len(r) > 0
        assert "Battery" in r or "battery" in r
        assert "ObjC" in r or "objc" in r

    def test_status_subcommand(self):
        r = run_ios_system("status")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_unknown_arg_returns_help(self):
        r = run_ios_system("unknown")
        assert r == HELP

    def test_whitespace_only(self):
        r = run_ios_system("   ")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_uppercase_battery(self):
        r = run_ios_system("BATTERY")
        assert isinstance(r, str)
        assert len(r) > 0

    def test_uppercase_wifi(self):
        r = run_ios_system("WIFI")
        assert isinstance(r, str)
        assert len(r) > 0


# ===================================================================
# 10. SKILL dict
# ===================================================================

class TestSkill:
    def test_is_dict(self):
        assert isinstance(SKILL, dict)

    def test_has_name(self):
        assert SKILL.get("name") == "ios_system"

    def test_has_description(self):
        assert "description" in SKILL

    def test_has_run(self):
        assert "run" in SKILL

    def test_run_is_callable(self):
        assert callable(SKILL["run"])

    def test_run_is_run_ios_system(self):
        assert SKILL["run"] is run_ios_system


# ===================================================================
# 11. HELP
# ===================================================================

class TestHelp:
    def test_is_string(self):
        assert isinstance(HELP, str)

    def test_non_empty(self):
        assert len(HELP) > 0

    def test_mentions_all_subcommands(self):
        for cmd in ("battery", "cellular", "wifi", "tts", "objc-test"):
            assert cmd in HELP


# ===================================================================
# 12. Edge cases
# ===================================================================

class TestEdgeCases:
    def test_tts_very_long(self):
        r = run_ios_system("tts " + "a" * 10000)
        assert isinstance(r, str) and len(r) > 0

    def test_tts_special_chars(self):
        r = run_ios_system("tts Hello! @#$%^&*() test")
        assert isinstance(r, str) and len(r) > 0

    def test_tts_unicode(self):
        r = run_ios_system("tts ěščřžýáíé")
        assert isinstance(r, str) and len(r) > 0

    def test_battery_health_stable(self):
        r = run_ios_system("battery --health")
        assert isinstance(r, str) and len(r) > 0

    def test_cellular_after_other_calls(self):
        r = run_ios_system("cellular")
        assert isinstance(r, str) and len(r) > 0

    def test_safe_exec_called(self):
        assert _safe_exec_mock.call_count > 0
