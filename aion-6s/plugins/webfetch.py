import re
import shlex
from core.jailbreak import safe_exec


def _strip_html(html):
    text = re.sub(r'(?is)<script[^>]*>.*?</script>', '', html)
    text = re.sub(r'(?is)<style[^>]*>.*?</style>', '', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def run_webfetch(args=""):
    url = args.strip()
    if not url:
        return "Usage: @plugin webfetch <url>"
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        result = safe_exec(f"curl -sL -H 'User-Agent: AION-6S/1.0' {shlex.quote(url)}", timeout=15)
        if not result["success"]:
            return f"Fetch failed: {result['stderr'][:200]}"
        text = result["stdout"].strip()
        text = _strip_html(text)
        text = text[:3000]
        return text if text else "(empty page)"
    except Exception as e:
        return f"Web fetch failed: {e}"


SKILL = {
    "name": "webfetch",
    "description": "Fetch and read a web page contents",
    "run": run_webfetch,
}
