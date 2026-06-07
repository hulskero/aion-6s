"""Shared pytest fixtures for AION-6S tests."""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mock_safe_exec():
    """Patch core.jailbreak.safe_exec with a configurable mock.

    Usage:
        def test_something(mock_safe_exec):
            mock_safe_exec.return_value = {"success": True, "stdout": "output", "stderr": "", "returncode": 0}
    """
    with patch("core.jailbreak.safe_exec") as mock:
        mock.return_value = {"success": True, "stdout": "", "stderr": "", "returncode": 0}
        yield mock


@pytest.fixture
def mock_ioreg():
    """Patch core.ios_hw.ioreg_get_first and ioreg_get_properties with realistic iPhone 6s data."""
    from tests.helpers.mock_ioreg import get_mock_props, BATTERY_PROPS, WIFI_PROPS, CELLULAR_PROPS, DISPLAY_PROPS, SENSOR_PROPS

    def _mock_get_first(class_name):
        props = get_mock_props(class_name)
        return props[0] if props else None

    def _mock_get_properties(class_name):
        return get_mock_props(class_name)

    with patch("core.ios_hw.ioreg_get_first", side_effect=_mock_get_first) as m1, \
         patch("core.ios_hw.ioreg_get_properties", side_effect=_mock_get_properties) as m2:
        yield {"get_first": m1, "get_properties": m2}


@pytest.fixture
def mock_bridge():
    """Patch core.bridge.Bridge with a configurable mock."""
    from tests.helpers.mock_bridge import MockBridge

    mock_instance = MockBridge()
    with patch("core.bridge.Bridge", return_value=mock_instance) as mock_class:
        yield mock_instance


@pytest.fixture
def clean_guardrails():
    """Reset core.guardrails global state before each test."""
    from core.guardrails import reset_confirm
    reset_confirm()
    yield
    reset_confirm()


@pytest.fixture
def clean_memory():
    """Provide a fresh MemoryManager instance."""
    from core.memory import MemoryManager
    return MemoryManager(max_pairs=5, max_tool_msgs=30)


@pytest.fixture
def sample_battery_data():
    """Realistic AppleARMPMU battery properties for iPhone 6s."""
    return {
        "BatteryInstalled": True,
        "CurrentCapacity": 1800,
        "MaxCapacity": 1715,
        "DesignCapacity": 1715,
        "CycleCount": 736,
        "Temperature": 3060,
        "Voltage": 4200,
        "IsCharging": False,
        "AppleRawCurrentCapacity": 1800,
        "AppleRawMaxCapacity": 1715,
    }


@pytest.fixture
def sample_wifi_data():
    """Realistic AppleBCMWLANCore WiFi properties for iPhone 6s."""
    return {
        "SSID": "TestNetwork",
        "BSSID": "aa:bb:cc:dd:ee:ff",
        "RSSI": -45,
        "CHANNEL": 6,
        "NOISE": -95,
        "txRate": 72,
    }


@pytest.fixture
def sample_cellular_data():
    """Realistic AppleBasebandPCI cellular properties for iPhone 6s."""
    return {
        "CarrierName": "Test Carrier",
        "FirmwareVersion": "1.2.3",
        "SignalStrength": -75,
        "IMEI": "012345678901234",
    }