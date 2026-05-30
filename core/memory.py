import gc

class MemoryManager:
    __slots__ = ["max_pairs", "context"]

    def __init__(self, max_pairs=5):
        self.max_pairs = max_pairs
        self.context = []

    def set_system(self, prompt):
        self.context = [{"role": "system", "content": prompt}]
        self.cleanup()

    def add(self, role, content):
        if not content:
            return
        self.context.append({"role": role, "content": content})
        sys_idx = 1 if len(self.context) > 1 and self.context[0]["role"] == "system" else 0
        max_msgs = self.max_pairs * 2
        if len(self.context) - sys_idx > max_msgs:
            keep = self.context[:sys_idx]
            keep += self.context[-(max_msgs):]
            self.context = keep
        self.cleanup()

    def get_context(self):
        return self.context

    def cleanup(self):
        gc.collect()
        gc.collect()

    def count_tokens(self):
        total = 0
        for msg in self.context:
            total += len(msg["content"])
        return total

    def reset(self):
        self.context = []
        gc.collect()
