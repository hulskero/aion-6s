import json
import os
import time
import random
import urllib.parse
import urllib.request
import urllib.error
import socket
import http.client
import threading
from collections import deque


class APIError(Exception):
    pass


class Bridge:
    __slots__ = [
        "api_key", "base_url", "model", "max_tokens", "temperature",
        "request_timeout", "rate_limit", "_retry_max", "_last_latency",
        "_last_usage", "_call_timestamps", "_network_ok", "_rlock",
    ]

    DEFAULTS = {
        "max_tokens": 256,
        "request_timeout": 200,
        "rate_limit": 30,
        "temperature": 0.1,
    }

    def __init__(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", self.DEFAULTS["max_tokens"])
        self.temperature = config.get("temperature", self.DEFAULTS["temperature"])
        self.request_timeout = config.get("request_timeout", self.DEFAULTS["request_timeout"])
        self.rate_limit = config.get("rate_limit", self.DEFAULTS["rate_limit"])
        self._retry_max = 5
        self._last_latency = 0
        self._last_usage = None
        self._call_timestamps = deque()
        self._network_ok = False
        self._rlock = threading.Lock()

    def update_config(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", self.DEFAULTS["max_tokens"])
        self.temperature = config.get("temperature", self.DEFAULTS["temperature"])
        self.request_timeout = config.get("request_timeout", self.DEFAULTS["request_timeout"])
        self.rate_limit = config.get("rate_limit", self.DEFAULTS["rate_limit"])
        self._network_ok = False
        self._call_timestamps.clear()

    def _enforce_rate_limit(self):
        if self.rate_limit <= 0:
            return
        now = time.time()
        cutoff = now - 60
        d = self._call_timestamps
        with self._rlock:
            while d and d[0] <= cutoff:
                d.popleft()
            if len(d) >= self.rate_limit:
                oldest = d[0]
                wait = 60 - (now - oldest)
                if wait > 0:
                    time.sleep(wait)

    def _wait_for_network(self, max_retries=3):
        if self._network_ok:
            return
        host = urllib.parse.urlparse(self.base_url).hostname
        port = urllib.parse.urlparse(self.base_url).port or 443
        for attempt in range(max_retries):
            try:
                sock = socket.create_connection((host, port), timeout=10)
                sock.close()
                self._network_ok = True
                return
            except (socket.timeout, OSError):
                self._network_ok = False
                if attempt == max_retries - 1:
                    raise APIError(f"Network timed out: {host}:{port}")
                time.sleep(5 + random.uniform(0, 3))

    def _build_opener(self):
        return urllib.request.build_opener()

    def _post(self, messages, stream=False):
        if not self.api_key:
            raise APIError(
                "No API key.\n"
                "  Set NVIDIA_API_KEY env var, or add \"api_key\" to config.json.\n"
                "  Get one at https://build.nvidia.com/deepseek-ai/deepseek-v4-flash"
            )
        self._wait_for_network()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Connection": "close",
            "User-Agent": "AION-6S/1.0",
            "Accept": "application/json",
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
            opener = self._build_opener()
            return opener.open(req, timeout=self.request_timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            code = e.code
            if code == 401:
                hint = " — Invalid API key"
            elif code == 403:
                hint = " — Authorization failed (check API key)"
            elif code == 429:
                hint = " — Rate limited, waiting..."
            elif code == 504:
                hint = " — NVIDIA Gateway Timeout (upstream overloaded)"
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

    def _retry_post(self, messages, stream=False):
        self._enforce_rate_limit()
        for attempt in range(self._retry_max):
            try:
                result = self._post(messages, stream)
                with self._rlock:
                    self._call_timestamps.append(time.time())
                return result
            except APIError as e:
                estr = str(e)
                if "401" in estr or "403" in estr or "Invalid API key" in estr:
                    raise
                if "504" in estr:
                    if attempt == self._retry_max - 1:
                        raise
                    wait = (attempt + 1) * 5 + random.uniform(0, 3)
                    time.sleep(wait)
                    continue
                if "429" in estr and attempt < self._retry_max - 1:
                    wait = (attempt + 1) * 10 + random.uniform(0, 5)
                    time.sleep(wait)
                    continue
                if "timed out" in estr.lower() or "unreachable" in estr.lower():
                    if attempt == self._retry_max - 1:
                        raise
                    wait = (attempt + 1) * 15 + random.uniform(0, 10)
                    time.sleep(wait)
                    continue
                if attempt == self._retry_max - 1:
                    raise
                wait = (attempt + 1) * 5 + random.uniform(0, 3)
                time.sleep(wait)
                continue

    def chat(self, messages):
        t0 = time.time()
        response = self._retry_post(messages, stream=False)
        try:
            try:
                raw = response.read()
                data = json.loads(raw)
            except (socket.timeout, ConnectionResetError, http.client.IncompleteRead,
                    ConnectionAbortedError, BrokenPipeError, OSError, json.JSONDecodeError) as e:
                raise APIError(f"Chat response read failed: {e}")
            self._last_latency = time.time() - t0
            if not isinstance(data, dict):
                raise APIError("Empty or non-dict API response")
            self._last_usage = data.get("usage")
            choices = data.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                raise APIError("API response missing choices")
            content = choices[0].get("message", {}).get("content")
            if content is None:
                raise APIError("API response missing content")
            return content
        finally:
            response.close()

    def stream(self, messages):
        t0 = time.time()
        response = self._retry_post(messages, stream=True)
        self._last_usage = None
        try:
            for retry in range(2):
                try:
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
                    break
                except (socket.timeout, urllib.error.URLError, ConnectionResetError,
                        http.client.RemoteDisconnected, ConnectionAbortedError,
                        BrokenPipeError, OSError, http.client.IncompleteRead) as e:
                    response.close()
                    if retry == 1:
                        raise APIError(f"Stream interrupted after retry: {e}")
                    response = self._retry_post(messages, stream=True)
        finally:
            response.close()
            self._last_latency = time.time() - t0

    def get_usage(self):
        return self._last_usage
