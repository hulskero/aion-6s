"""Mock Bridge class and factory for testing."""

import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from core.bridge import APIError


class MockBridge:
    """Mock Bridge for testing without network calls."""

    def __init__(self, chat_response="Test AI response", stream_chunks=None, should_fail=False, fail_error=None):
        self.chat_response = chat_response
        self.stream_chunks = stream_chunks or ["chunk1", "chunk2", "chunk3"]
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.call_count = 0
        self._last_usage = None

    def chat(self, messages):
        self.call_count += 1
        if self.should_fail:
            error = self.fail_error or APIError("Mock bridge error")
            raise error
        return self.chat_response

    def stream(self, messages):
        self.call_count += 1
        if self.should_fail:
            error = self.fail_error or APIError("Mock bridge error")
            raise error
        for chunk in self.stream_chunks:
            yield chunk

    def get_usage(self):
        return self._last_usage


@contextmanager
def mock_bridge(chat_response="Test AI response", stream_chunks=None, should_fail=False, fail_error=None):
    """Context manager that patches core.bridge.Bridge.

    Usage:
        with mock_bridge(chat_response="Hello!"):
            bridge = Bridge({})
            result = bridge.chat([{"role": "user", "content": "hi"}])
    """
    mock_instance = MockBridge(
        chat_response=chat_response,
        stream_chunks=stream_chunks,
        should_fail=should_fail,
        fail_error=fail_error,
    )
    with patch("core.bridge.Bridge", return_value=mock_instance) as mock_class:
        yield mock_instance


@contextmanager
def mock_bridge_factory(responses):
    """Create a Bridge mock with a sequence of responses.

    Usage:
        with mock_bridge_factory(["first", "second", APIError("fail")]):
            bridge = Bridge({})
            bridge.chat(...)  # "first"
            bridge.chat(...)  # "second"
            bridge.chat(...)  # raises APIError
    """
    iterator = iter(responses)

    def _chat(*args, **kwargs):
        result = next(iterator)
        if isinstance(result, Exception):
            raise result
        return result

    mock = MagicMock()
    mock.chat.side_effect = _chat
    mock.stream.side_effect = _chat
    mock.get_usage.return_value = None

    with patch("core.bridge.Bridge", return_value=mock):
        yield mock