"""Reusable mock IOKit data for iPhone 6s (iOS 10-12)."""

BATTERY_PROPS = [{
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
    "ExternalConnected": False,
    "FullyCharged": False,
}]

WIFI_PROPS = [{
    "SSID": "TestNetwork",
    "BSSID": "aa:bb:cc:dd:ee:ff",
    "RSSI": -45,
    "CHANNEL": 6,
    "NOISE": -95,
    "txRate": 72,
    "maxLinkSpeed": 144,
    "SSID_STR": "TestNetwork",
}]

CELLULAR_PROPS = [{
    "CarrierName": "Test Carrier",
    "FirmwareVersion": "1.2.3",
    "SignalStrength": -75,
    "IMEI": "012345678901234",
    "ICCID": "8944200000000000000F",
    "IMEI2": "012345678901235",
    "EID": "32145678901234567890123456789012",
}]

DISPLAY_PROPS = [{
    "displayPixelRows": 1334,
    "displayPixelColumns": 750,
    "displayScale": 2,
    "IODisplayEDID": b"dummy_edid_data",
}]

SENSOR_PROPS = [
    {
        "IOKitClass": "AppleARMPMU",
        "temperature": 306,
        "voltage": 4200,
        "current": 250,
    },
    {
        "IOKitClass": "AppleEmbeddedI2CLightSensor",
        "illuminance": 500,
    },
    {
        "IOKitClass": "AppleSPUHIDDevice",
        "name": "accel",
        "x": 0.1,
        "y": -0.2,
        "z": 9.81,
    },
    {
        "IOKitClass": "AppleSPUHIDDevice",
        "name": "gyro",
        "x": 0.01,
        "y": 0.02,
        "z": -0.01,
    },
    {
        "IOKitClass": "AppleSPUHIDDevice",
        "name": "baro",
        "pressure": 101325,
    },
]


def get_mock_props(class_name):
    """Return mock properties for the given IOKit class name."""
    mapping = {
        "AppleSmartBattery": BATTERY_PROPS,
        "AppleARMPMU": BATTERY_PROPS + SENSOR_PROPS[:1],
        "IO80211Interface": WIFI_PROPS,
        "AppleBCMWLANCore": WIFI_PROPS,
        "AppleBasebandPCI": CELLULAR_PROPS,
        "AppleBaseband": CELLULAR_PROPS,
        "AppleCLCD": DISPLAY_PROPS,
        "AppleMobileADBE0": DISPLAY_PROPS,
        "AppleEmbeddedI2CLightSensor": [SENSOR_PROPS[1]],
        "AppleSPUHIDDevice": SENSOR_PROPS[2:],
        "AppleSPU": SENSOR_PROPS[2:],
    }
    return mapping.get(class_name, [])


def get_mock_props_by_path(path):
    """Return mock properties based on the IORegistry path."""
    if "AppleSmartBattery" in path:
        return BATTERY_PROPS
    if "AppleARMPMU" in path:
        return BATTERY_PROPS + SENSOR_PROPS[:1]
    if "IO80211" in path or "AppleBCMWLAN" in path:
        return WIFI_PROPS
    if "AppleBaseband" in path:
        return CELLULAR_PROPS
    if "AppleCLCD" in path or "AppleMobileADBE" in path:
        return DISPLAY_PROPS
    if "AppleEmbeddedI2CLightSensor" in path:
        return [SENSOR_PROPS[1]]
    if "AppleSPUHID" in path or "AppleSPU" in path:
        return SENSOR_PROPS[2:]
    return []