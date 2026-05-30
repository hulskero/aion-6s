class SelfHeal:
    __slots__ = ["bridge", "max_tries", "history"]

    def __init__(self, bridge, max_tries=3):
        self.bridge = bridge
        self.max_tries = max_tries
        self.history = []

    def heal(self, cmd, stderr):
        self.history.append({"cmd": cmd, "error": stderr})

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
                return None
            if fix.startswith("@cmd "):
                fix = fix[5:]
            return fix

        return None

    def summary(self):
        if not self.history:
            return "No healing events."
        lines = [f"  Healed {len(self.history)} error(s):"]
        for h in self.history:
            lines.append(f"    {h['cmd'][:60]} -> {h['error'][:60]}")
        return "\n".join(lines)
