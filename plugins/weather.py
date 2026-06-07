import json
import logging
import shlex
import urllib.parse
from core.jailbreak import safe_exec

LOGGER = logging.getLogger(__name__)

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
    loc_enc = urllib.parse.quote(location, safe=",") if location else ""
    url = f"https://wttr.in/{loc_enc}?format=%l:+%C,+%t,+%w,+%h&m" if location else "https://wttr.in/?format=%l:+%C,+%t,+%w,+%h&m"
    try:
        r = safe_exec(f"curl -sL -H 'User-Agent: AION-6S/1.0' {shlex.quote(url)}", timeout=8)
        if r["success"] and r["stdout"].strip():
            return r["stdout"].strip()
    except Exception:
        LOGGER.debug("wttr.in weather fetch failed")
    return None

def _openmeteo(location):
    try:
        loc_enc = urllib.parse.quote(location, safe="")
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={loc_enc}&count=1"
        r = safe_exec(f"curl -sL -H 'User-Agent: AION-6S/1.0' {shlex.quote(geo_url)}", timeout=8)
        if not r["success"] or not r["stdout"].strip():
            return None
        geo = json.loads(r["stdout"])
        if not geo.get("results"):
            return None
        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]
        loc_name = geo["results"][0]["name"]
        fc_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m"
        r2 = safe_exec(f"curl -sL -H 'User-Agent: AION-6S/1.0' {shlex.quote(fc_url)}", timeout=8)
        if not r2["success"] or not r2["stdout"].strip():
            return None
        data = json.loads(r2["stdout"])
        w = data["current"]
        code = WMO_CODES.get(w["weather_code"], f"Code {w['weather_code']}")
        return f"{loc_name}: {w['temperature_2m']}°C, {code}, wind {w['wind_speed_10m']} km/h"
    except Exception:
        LOGGER.debug("open-meteo weather fetch failed")
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
