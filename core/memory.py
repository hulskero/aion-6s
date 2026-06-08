import gc
import threading


class MemoryManager:
    __slots__ = ["max_pairs", "max_tool_msgs", "context", "_msg_count", "_total_bytes", "max_total_bytes", "_lock"]

    def __init__(self, max_pairs=5, max_tool_msgs=30):
        self.max_pairs = max_pairs
        self.max_tool_msgs = max_tool_msgs
        self.max_total_bytes = 262144
        self._total_bytes = 0
        self._lock = threading.Lock()
        self.context = []
        self._msg_count = 0

    def set_system(self, prompt):
        with self._lock:
            self.context = [{"role": "system", "content": prompt}]
            self._msg_count = 0
            self._total_bytes = len(prompt)

    def add(self, role, content):
        if not content:
            return
        with self._lock:
            self.context.append({"role": role, "content": content})
            self._msg_count += 1
            self._total_bytes += len(content)
            if self.max_pairs <= 0:
                self._trim_tool_msgs()
                return
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
            if self._total_bytes > self.max_total_bytes:
                self._trim_to_byte_target()
            self._trim_tool_msgs()
            self._smart_gc()

    def _trim_tool_msgs(self):
        tool_indices = [i for i, m in enumerate(self.context)
                        if m.get("role") == "tool"]
        if len(tool_indices) > self.max_tool_msgs:
            excess = len(tool_indices) - self.max_tool_msgs
            keep = []
            trim_count = 0
            for i, m in enumerate(self.context):
                if trim_count < excess and m.get("role") == "tool":
                    trim_count += 1
                    continue
                keep.append(m)
            self.context = keep

    def get_context(self):
        return self.context

    def _trim_to_byte_target(self):
        target = self.max_total_bytes // 2
        sys_idx = 1 if len(self.context) > 1 and self.context[0]["role"] == "system" else 0
        while self._total_bytes > target and len(self.context) > sys_idx:
            msg = self.context.pop(sys_idx)
            self._total_bytes -= len(msg.get("content", ""))
        self._smart_gc()

    def _smart_gc(self):
        if self._msg_count % 20 == 0:
            gc.collect()
        elif self._total_bytes > int(self.max_total_bytes * 0.75):
            gc.collect()

    def cleanup(self):
        with self._lock:
            sys_idx = 1 if len(self.context) > 1 and self.context[0]["role"] == "system" else 0
            user_assistant = [m for m in self.context[sys_idx:] if m["role"] in ("user", "assistant")]
            max_allowed = self.max_pairs * 2
            if len(user_assistant) > max_allowed:
                excess = len(user_assistant) - max_allowed
                keep = self.context[:sys_idx]
                for msg in self.context[sys_idx:]:
                    if excess > 0 and msg["role"] in ("user", "assistant"):
                        excess -= 1
                        continue
                    keep.append(msg)
                self.context = keep
            self._msg_count = len(self.context)
            self._total_bytes = sum(len(m.get("content", "")) for m in self.context)
            if self._total_bytes > self.max_total_bytes:
                self._trim_to_byte_target()
            self._trim_tool_msgs()
            self._smart_gc()

    def count_chars(self):
        total = 0
        for msg in self.context:
            total += len(msg["content"])
        return total

    def reset(self):
        self.context = []
        self._msg_count = 0
        self._total_bytes = 0
        gc.collect()
