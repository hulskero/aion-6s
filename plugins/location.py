import subprocess
import json


def run_location(args=""):
    try:
        result = subprocess.run(
            ["curl", "-sL", "ipinfo.io/json"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        city = data.get("city", "?")
        region = data.get("region", "?")
        country = data.get("country", "?")
        ip = data.get("ip", "?")
        org = data.get("org", "?")
        return f"Location: {city}, {region}, {country}  |  IP: {ip}  |  ISP: {org}"
    except Exception as e:
        return f"Location check failed: {e}"


SKILL = {
    "name": "location",
    "description": "Get approximate location via IP (city, country, ISP)",
    "run": run_location,
}
