import json
import subprocess

WMO_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

def _wttrin(location):
    url = f"https://wttr.in/{location}?format=%l:+%C,+%t,+%w,+%h&m" if location else "https://wttr.in/?format=%l:+%C,+%t,+%w,+%h&m"
    try:
        r = subprocess.run(["curl", "-sL", "-H", "User-Agent: AION-6S/1.0", url], capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None

def _openmeteo(location):
    try:
        r = subprocess.run(
            ["curl", "-sL", "-H", "User-Agent: AION-6S/1.0", f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        geo = json.loads(r.stdout)
        if not geo.get("results"):
            return None
        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]
        loc_name = geo["results"][0]["name"]
        r2 = subprocess.run(
            ["curl", "-sL", "-H", "User-Agent: AION-6S/1.0", f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m"],
            capture_output=True, text=True, timeout=8
        )
        if r2.returncode != 0 or not r2.stdout.strip():
            return None
        data = json.loads(r2.stdout)
        w = data["current"]
        code = WMO_CODES.get(w["weather_code"], f"Code {w['weather_code']}")
        return f"{loc_name}: {w['temperature_2m']}°C, {code}, wind {w['wind_speed_10m']} km/h"
    except Exception:
        pass
    return None

def run_weather(args=""):
    location = args.strip() or ""
    if not location:
        result = _wttrin("")
        if result:
            return result
        return "Weather unavailable (wttr.in down, no location for fallback)"
    result = _wttrin(location)
    if result:
        return result
    result = _openmeteo(location)
    if result:
        return result
    return f"Weather unavailable for '{location}'"


SKILL = {
    "name": "weather",
    "description": "Get current weather for a city",
    "run": run_weather,
}
