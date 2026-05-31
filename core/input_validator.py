"""
Input validation utilities for AION-6S.
Provides functions for sanitizing user input and LLM-generated content
to prevent injection attacks and ensure safe operation.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from typing import Optional, Tuple


def sanitize_input(
    text: str,
    max_length: int = 500,
    whitelist_regex: str = r'^[a-zA-Z0-9\s.,:_/@-]+$',
    allow_empty: bool = False
) -> Optional[str]:
    """
    Sanitize input string: length limit and whitelist validation.

    Args:
        text: Input string to sanitize
        max_length: Maximum allowed length
        whitelist_regex: Regex pattern for allowed characters
        allow_empty: Whether empty strings are allowed

    Returns:
        Sanitized string if valid, otherwise None
    """
    if not isinstance(text, str):
        return None

    # Handle empty string
    if not text:
        return "" if allow_empty else None

    if len(text) > max_length:
        return None

    if not re.match(whitelist_regex, text):
        return None

    return text


def safe_shell_split(command: str) -> Optional[list[str]]:
    """
    Safely split a command string into arguments using shlex.
    Returns None if the command contains unsafe quoting or cannot be parsed.

    Args:
        command: Command string to split

    Returns:
        List of arguments if successful, None otherwise
    """
    try:
        parts = shlex.split(command)
        return parts if parts else None
    except ValueError:
        # Invalid quoting (e.g., mismatched quotes)
        return None


def safe_subprocess_run(
    command: str,
    timeout: int = 30,
    shell: bool = False
) -> dict:
    """
    Safely run a subprocess command with protections against injection.

    Args:
        command: Command to execute
        timeout: Timeout in seconds
        shell: Whether to use shell (should be False for security)

    Returns:
        Dictionary with success, stdout, stderr, and return code
    """
    if shell:
        # If shell=True is absolutely necessary, at least sanitize the command
        sanitized_cmd = sanitize_input(command, max_length=1000)
        if not sanitized_cmd:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Input validation failed: command contains invalid characters",
                "returncode": -1
            }
        args = sanitized_cmd
    else:
        # Use safe splitting to avoid shell injection
        args = safe_shell_split(command)
        if args is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Invalid command: unable to parse arguments safely",
                "returncode": -1
            }

    try:
        result = subprocess.run(
            args,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {args[0] if args else 'unknown'}",
            "returncode": 127
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unexpected error: {str(e)}",
            "returncode": -1
        }


def validate_command_args(args: list[str]) -> Tuple[bool, str]:
    """
    Validate command arguments against a whitelist of safe commands.

    Args:
        args: List of command arguments (first element is the command)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not args or not isinstance(args, list):
        return False, "Invalid arguments: expected non-empty list"

    command = args[0]

    # Whitelist of safe commands for AION-6S
    SAFE_COMMANDS = {
        # System info — a-Shell compatible
        'uname', 'df', 'hostname', 'id', 'whoami', 'pwd', 'date', 'uptime',
        # Network
        'curl', 'ping', 'nslookup', 'dig', 'ifconfig', 'netstat',
        # Filesystem
        'ls', 'cat', 'echo', 'head', 'tail', 'wc', 'sort', 'grep', 'awk', 'sed',
        'cp', 'mv', 'mkdir', 'rm', 'touch', 'chmod', 'chown',
        'find', 'basename', 'dirname', 'realpath',
        # iOS / a-Shell
        'open', 'sbreload', 'uicache',
        # Scripting
        'python3', 'python', 'printenv', 'env',
        # Editors
        'vim', 'pico', 'ed', 'nano',
        # Process
        'ps', 'kill', 'pkill',
        # Disk
        'mount', 'stat', 'du',
    }

    if command not in SAFE_COMMANDS:
        return False, f"Command '{command}' is not in the allowed commands list"

    return True, ""


# Export public functions
__all__ = [
    'sanitize_input',
    'safe_shell_split',
    'safe_subprocess_run',
    'validate_command_args'
]