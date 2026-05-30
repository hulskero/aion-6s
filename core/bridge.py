import json
import os
import time
import urllib.request
import urllib.error


class APIError(Exception):
    pass


class Bridge:
    __slots__ = [
        "api_key", "base_url", "model", "max_tokens", "temperature",
        "request_timeout", "rate_limit", "_retry_max", "_last_latency",
        "_call_timestamps",
    ]

    def __init__(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.7)
        self.request_timeout = config.get("request_timeout", 120)
        self.rate_limit = config.get("rate_limit", 30)
        self._retry_max = 3
        self._last_latency = 0
        self._call_timestamps = []

    def update_config(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.7)
        self.request_timeout = config.get("request_timeout", 120)
        self.rate_limit = config.get("rate_limit", 30)

    def _enforce_rate_limit(self):
        now = time.time()
        window = 60
        cutoff = now - window
        self._call_timestamps = [t for t in self._call_timestamps if t > cutoff]
        if len(self._call_timestamps) >= self.rate_limit:
            oldest = self._call_timestamps[0]
            wait = window - (now - oldest)
            if wait > 0:
                time.sleep(wait)
        self._call_timestamps.append(time.time())

    def _post(self, messages, stream=False):
        if not self.api_key:
            raise APIError(
                "No API key.\n"
                "  Set NVIDIA_API_KEY env var, or add \"api_key\" to config.json.\n"
                "  Get one at https://build.nvidia.com/deepseek-ai/deepseek-v4-flash"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body, headers=headers, method="POST"
        )
        try:
            return urllib.request.urlopen(req, timeout=self.request_timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise APIError(f"HTTP {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise APIError(f"Network: {e.reason}")

    def _retry_post(self, messages, stream=False):
        self._enforce_rate_limit()
        for attempt in range(self._retry_max):
            try:
                return self._post(messages, stream)
            except APIError as e:
                # Check for rate limit (429) and wait longer
                if "429" in str(e) and attempt < self._retry_max - 1:
                    wait = (attempt + 1) * 10  # Longer wait for rate limiting
                    time.sleep(wait)
                    continue
                if attempt == self._retry_max - 1:
                    raise
                wait = (attempt + 1) * 2
                time.sleep(wait)

    def chat(self, messages):
        t0 = time.time()
        response = self._retry_post(messages, stream=False)
        data = json.loads(response.read())
        self._last_latency = time.time() - t0
        return data["choices"][0]["message"]["content"]

    def stream(self, messages):
        t0 = time.time()
        response = self._retry_post(messages, stream=True)
        for line_bytes in response:
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"]
                    content = delta.get("content")
                    if content is not None:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        self._last_latency = time.time() - t0
