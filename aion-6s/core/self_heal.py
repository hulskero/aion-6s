import hashlib
import json
import logging
import os
import re

LOGGER = logging.getLogger(__name__)

_MAX_HEAL_HISTORY = 200


SENSITIVE_PATTERNS = [
    (r'/var/mobile/[A-Za-z0-9\-]+/', '/var/mobile/***/'),
    (r'/Users/\w+/', '/Users/***/'),
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***.***.***.***'),
    (r'nvapi-[A-Za-z0-9]+', 'nvapi-***'),
    (r'sk-[A-Za-z0-9]+', 'sk-***'),
    (r'ghp_[A-Za-z0-9]+', 'ghp_***'),
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '***@***'),
]


def sanitize(text):
    for pat, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pat, replacement, text)
    return text


IOS_ABSENT = ["free", "wlanconfig", "system_profiler"]


class SelfHeal:
    __slots__ = ["bridge", "max_tries", "history", "_cache", "_cache_path"]

    def __init__(self, bridge, max_tries=3):
        self.bridge = bridge
        self.max_tries = max_tries
        self.history = []
        self._cache_path = os.path.join(os.path.dirname(__file__), "..", "heal_cache.json")
        self._cache = self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path) as f:
                    return json.load(f)
        except Exception:
            LOGGER.debug("heal cache load failed")
        return {}

    def _save_cache(self):
        try:
            if len(self._cache) > 1000:
                for k in list(self._cache)[:-500]:
                    del self._cache[k]
            tmp = self._cache_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._cache, f, indent=2)
            os.replace(tmp, self._cache_path)
        except Exception:
            LOGGER.warning("heal cache save failed")

    def heal(self, cmd, stderr):
        cmd_s = sanitize(cmd)
        err_s = sanitize(stderr)
        self.history.append({"cmd": cmd_s, "error": err_s})
        if len(self.history) > _MAX_HEAL_HISTORY:
            self.history = self.history[-_MAX_HEAL_HISTORY:]

        for absent in IOS_ABSENT:
            if absent in cmd_s and "not found" in err_s.lower():
                self._cache[hashlib.md5(cmd_s.encode()).hexdigest()] = f"FAIL {absent} not available on iOS"
                self._save_cache()
                return None

        cache_key = hashlib.md5((cmd_s.strip() + err_s.strip()[-300:]).encode()).hexdigest()
        cached = self._cache.get(cache_key)
        if cached:
            if not cached.startswith("FAIL"):
                return cached

        for attempt in range(self.max_tries):
            prompt = f"""Command failed. Fix it.

CMD: {cmd_s}
ERR: {err_s}

Output ONLY the fixed shell command, nothing else.
If impossible, output: FAIL <reason>"""
            try:
                fix = self.bridge.chat([
                    {"role": "system", "content": "Output ONLY the fixed command or FAIL <reason>."},
                    {"role": "user", "content": prompt},
                ])
            except Exception:
                self._cache[cache_key] = "FAIL api_error"
                self._save_cache()
                return None
            fix = fix.strip().strip("`").strip()
            if fix.startswith("FAIL") or fix.startswith("@FAIL"):
                self._cache[cache_key] = f"FAIL {fix}"
                self._save_cache()
                return None
            if fix.startswith("@cmd "):
                fix = fix[5:]
            self._cache[cache_key] = fix
            self._save_cache()
            return fix

        return None

    def summary(self):
        if not self.history:
            return "No healing events."
        cached = len(self._cache)
        lines = [f"  Healed {len(self.history)} error(s)  |  {cached} cached fix(es):"]
        for h in self.history[-5:]:
            lines.append(f"    {h['cmd'][:60]} -> {h['error'][:60]}")
        return "\n".join(lines)
