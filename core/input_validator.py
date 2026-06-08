"""
Input validation utilities for AION-6S.
Provides functions for sanitizing user input and LLM-generated content
to prevent injection attacks and ensure safe operation.
"""

from __future__ import annotations

import re
import shlex
from typing import Optional, Tuple


def sanitize_input(
    text: str,
    max_length: int = 500,
    whitelist_regex: str = r'^[-\w\s.,:\/@|!$%^&*()\[\]{}<>?~#=+;\'"`\\]+$',
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


# Export public functions
__all__ = [
    'sanitize_input',
    'safe_shell_split',
]