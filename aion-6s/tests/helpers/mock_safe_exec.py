"""Factory functions for safe_exec mocks."""

import subprocess
from contextlib import contextmanager
from unittest.mock import patch


def make_safe_exec_ok(stdout="", stderr="", returncode=0):
    """Create a safe_exec mock that returns success."""
    return {"success": True, "stdout": stdout, "stderr": stderr, "returncode": returncode}


def make_safe_exec_fail(stderr="command failed", returncode=1):
    """Create a safe_exec mock that returns failure."""
    return {"success": False, "stdout": "", "stderr": stderr, "returncode": returncode}


def make_safe_exec_timeout():
    """Create a side_effect that raises TimeoutExpired."""
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0] if args else "cmd", kwargs.get("timeout", 8))
    return _raise_timeout


@contextmanager
def mock_safe_exec(side_effect=None, return_value=None):
    """Context manager that patches core.jailbreak.safe_exec.

    Usage:
        with mock_safe_exec(return_value={"success": True, "stdout": "hi"}):
            result = safe_exec("some command")
    """
    patcher = patch("core.jailbreak.safe_exec")
    mock = patcher.start()
    try:
        if side_effect is not None:
            mock.side_effect = side_effect
        elif return_value is not None:
            mock.return_value = return_value
        else:
            mock.return_value = {"success": True, "stdout": "", "stderr": "", "returncode": 0}
        yield mock
    finally:
        patcher.stop()


def mock_safe_exec_factory(responses):
    """Create a safe_exec mock that returns different values for each call.

    Usage:
        mock = mock_safe_exec_factory([
            {"success": True, "stdout": "first"},
            {"success": True, "stdout": "second"},
            make_safe_exec_fail("error"),
        ])
        with patch("core.jailbreak.safe_exec", mock):
            ...
    """
    from unittest.mock import MagicMock
    mock = MagicMock(side_effect=responses)
    return mock