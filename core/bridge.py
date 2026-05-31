import json
import os
import time
import urllib.request
import urllib.error
import socket
import ssl


class APIError(Exception):
    pass


class Bridge:
    __slots__ = [
        "api_key", "base_url", "model", "max_tokens", "temperature",
        "request_timeout", "rate_limit", "_retry_max", "_last_latency",
        "_last_usage", "_call_timestamps",
    ]

    DEFAULTS = {
        "max_tokens": 512,
        "request_timeout": 90,
        "rate_limit": 30,
        "temperature": 0.7,
    }

    def __init__(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", self.DEFAULTS["max_tokens"])
        self.temperature = config.get("temperature", self.DEFAULTS["temperature"])
        self.request_timeout = config.get("request_timeout", self.DEFAULTS["request_timeout"])
        self.rate_limit = config.get("rate_limit", self.DEFAULTS["rate_limit"])
        self._retry_max = 3
        self._last_latency = 0
        self._last_usage = None
        self._call_timestamps = []

    def update_config(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", self.DEFAULTS["max_tokens"])
        self.temperature = config.get("temperature", self.DEFAULTS["temperature"])
        self.request_timeout = config.get("request_timeout", self.DEFAULTS["request_timeout"])
        self.rate_limit = config.get("rate_limit", self.DEFAULTS["rate_limit"])

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
            code = e.code
            if code == 401:
                hint = " — Invalid API key"
            elif code == 403:
                hint = " — Authorization failed (check API key)"
            elif code == 429:
                hint = " — Rate limited, waiting..."
            elif code >= 500:
                hint = " — NVIDIA API error (try again)"
            else:
                hint = ""
            raise APIError(f"HTTP {code}: {detail}{hint}")
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "timed out" in reason.lower():
                hint = " — Connection timed out (check network / VPN)"
            elif "no address" in reason.lower() or "name or service not known" in reason.lower():
                hint = " — DNS failed (check internet)"
            elif "connection refused" in reason.lower():
                hint = " — Connection refused (API down?)"
            elif "certificate" in reason.lower() or "cert" in reason.lower():
                hint = " — SSL error (bad certificate)"
            else:
                hint = ""
            raise APIError(f"Network: {reason}{hint}")
        except socket.timeout:
            raise APIError("Socket timed out — check your network connection")

    def _retry_post(self, messages, stream=False):
        self._enforce_rate_limit()
        for attempt in range(self._retry_max):
            try:
                return self._post(messages, stream)
            except APIError as e:
                estr = str(e)
                if "401" in estr or "403" in estr or "Invalid API key" in estr:
                    raise
                if "429" in estr and attempt < self._retry_max - 1:
                    wait = (attempt + 1) * 10
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
        self._last_usage = None
        for line_bytes in response:
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    if "usage" in chunk:
                        self._last_usage = chunk["usage"]
                    delta = chunk["choices"][0]["delta"]
                    content = delta.get("content")
                    if content is not None:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        self._last_latency = time.time() - t0

    def get_usage(self):
        return getattr(self, "_last_usage", None)
