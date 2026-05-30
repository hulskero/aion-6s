import json
import os
import urllib.request
import urllib.error


class APIError(Exception):
    pass


class Bridge:
    __slots__ = ["api_key", "base_url", "model", "max_tokens", "temperature"]

    def __init__(self, config):
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.model = config.get("model", "deepseek-ai/deepseek-v4-flash")
        self.max_tokens = config.get("max_tokens", 4096)
        self.temperature = config.get("temperature", 0.7)

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
            return urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise APIError(f"HTTP {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise APIError(f"Network: {e.reason}")

    def chat(self, messages):
        response = self._post(messages, stream=False)
        data = json.loads(response.read())
        return data["choices"][0]["message"]["content"]

    def stream(self, messages):
        response = self._post(messages, stream=True)
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
                    if "content" in delta:
                        yield delta["content"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
