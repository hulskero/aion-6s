import subprocess
import json
import os
import re

GPS_FILE = os.path.expanduser("~/Documents/gps.json")


def _ip_location():
    """Fallback: city-level location via IP."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "-H", "User-Agent: AION-6S/1.0", "ipinfo.io/json"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(r.stdout)
        city = data.get("city", "?")
        region = data.get("region", "?")
        country = data.get("country", "?")
        ip = data.get("ip", "?")
        org = data.get("org", "?")
        return f"Approximate: {city}, {region}, {country}  |  IP: {ip}  |  ISP: {org}"
    except Exception as e:
        return None


def _gps_file():
    """Read GPS from file written by iOS Shortcut."""
    if not os.path.exists(GPS_FILE):
        return None
    try:
        data = json.loads(open(GPS_FILE).read())
        lat = data.get("lat")
        lon = data.get("lon")
        acc = data.get("accuracy", "?")
        ts = data.get("timestamp", "?")
        if lat is not None and lon is not None:
            return f"GPS: {lat}, {lon}  |  accuracy: ±{acc}m  |  at: {ts}"
    except Exception:
        pass
    return None


def _trigger_gps_shortcut():
    """Open Shortcuts to request GPS fix."""
    try:
        subprocess.run(
            ["open", "shortcuts://run-shortcut?name=GPS2File&input=text&text=get"],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        return False


GPS_HELP = """\
GPS requires a Shortcut:
  Name: GPS2File
  Steps: Get Current Location → Get Details (Lat, Lon, Accuracy) →
         Combine as JSON → Save to iCloud Drive/AION/gps.json
  (a-Shell reads ~/Documents/gps.json which iCloud syncs)

Once created, run @plugin location gps — first time triggers Shortcut,
second time reads the file.

Alternatively set GPS_LOOP in the Shortcut to poll and write repeatedly.
"""


def run_location(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "gps":
        result = _gps_file()
        if result:
            return result
        triggered = _trigger_gps_shortcut()
        if triggered:
            return "GPS: opened Shortcuts — run @plugin location gps again after it completes"
        return "GPS: no saved GPS data. Create 'GPS2File' Shortcut (see /help location)"

    if subcmd == "help":
        return GPS_HELP

    return _ip_location() or "Location unavailable"


SKILL = {
    "name": "location",
    "description": "Get location — IP city-level (default), or @plugin location gps for precise GPS via Shortcut",
    "run": run_location,
}
