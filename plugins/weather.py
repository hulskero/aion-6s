import subprocess


def run_weather(args=""):
    location = args.strip() or ""
    url = f"wttr.in/{location}?format=%l:+%C,+%t,+%w,+%h&m" if location else "wttr.in/?format=%l:+%C,+%t,+%w,+%h&m"
    try:
        result = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "Weather unavailable"
    except Exception as e:
        return f"Weather check failed: {e}"


SKILL = {
    "name": "weather",
    "description": "Get current weather for a city",
    "run": run_weather,
}
