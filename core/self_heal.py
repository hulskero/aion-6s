import json
import os


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
            pass
        return {}

    def _save_cache(self):
        try:
            with open(self._cache_path, "w") as f:
                json.dump(self._cache, f, indent=2)
        except Exception:
            pass

    def heal(self, cmd, stderr):
        self.history.append({"cmd": cmd, "error": stderr})

        cache_key = stderr.strip()[-200:]
        cached = self._cache.get(cache_key)
        if cached and cached != cmd:
            if not cached.startswith("FAIL"):
                return cached

        for attempt in range(self.max_tries):
            prompt = f"""Command failed. Fix it.

CMD: {cmd}
ERR: {stderr}

Output ONLY the fixed shell command, nothing else.
If impossible, output: FAIL <reason>"""
            fix = self.bridge.chat([
                {"role": "system", "content": "Output ONLY the fixed command or FAIL <reason>."},
                {"role": "user", "content": prompt},
            ])
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
