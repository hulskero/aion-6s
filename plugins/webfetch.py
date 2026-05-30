import subprocess
import re


def run_webfetch(args=""):
    url = args.strip()
    if not url:
        return "Usage: @plugin webfetch <url>"
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Fetch failed: {result.stderr[:200]}"
        text = result.stdout.strip()
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        text = text[:2000]
        return text if text else "(empty page)"
    except Exception as e:
        return f"Web fetch failed: {e}"


SKILL = {
    "name": "webfetch",
    "description": "Fetch and read a web page contents",
    "run": run_webfetch,
}
