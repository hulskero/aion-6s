import gc


class MemoryManager:
    __slots__ = ["max_pairs", "context", "_msg_count"]

    def __init__(self, max_pairs=5):
        self.max_pairs = max_pairs
        self.context = []
        self._msg_count = 0

    def set_system(self, prompt):
        self.context = [{"role": "system", "content": prompt}]
        self._msg_count = 0

    def add(self, role, content):
        if not content:
            return
        self.context.append({"role": role, "content": content})
        self._msg_count += 1
        sys_idx = 1 if len(self.context) > 1 and self.context[0]["role"] == "system" else 0
        user_assistant = [m for m in self.context[sys_idx:] if m["role"] in ("user", "assistant")]
        max_pairs = self.max_pairs * 2
        if len(user_assistant) > max_pairs:
            excess = len(user_assistant) - max_pairs
            keep = self.context[:sys_idx]
            for msg in self.context[sys_idx:]:
                if excess > 0 and msg["role"] in ("user", "assistant"):
                    excess -= 1
                    continue
                keep.append(msg)
            self.context = keep
        self._smart_gc()

    def get_context(self):
        return self.context

    def _smart_gc(self):
        if self._msg_count % 5 == 0:
            gc.collect()
            gc.collect()

    def cleanup(self):
        if self._msg_count % 3 == 0:
            gc.collect()

    def count_chars(self):
        total = 0
        for msg in self.context:
            total += len(msg["content"])
        return total

    def reset(self):
        self.context = []
        self._msg_count = 0
        gc.collect()
