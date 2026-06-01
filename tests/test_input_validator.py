"""
Unit tests for input validator module.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from input_validator import sanitize_input, safe_shell_split


def test_sanitize_input():
    """Test input sanitization function."""
    # Test valid input
    assert sanitize_input("hello world") == "hello world"
    assert sanitize_input("test@example.com") == "test@example.com"  # @ allowed in whitelist
    assert sanitize_input("ls -la") == "ls -la"  # hyphen and space allowed in whitelist

    # Test length limit
    long_string = "a" * 501
    assert sanitize_input(long_string) is None

    # Test whitelist with different regex
    assert sanitize_input("ls -la", whitelist_regex=r'^[a-zA-Z0-9\s\-]+$') == "ls -la"
    assert sanitize_input("ls; rm -rf /", whitelist_regex=r'^[a-zA-Z0-9\s\-]+$') is None

    # Test empty string
    assert sanitize_input("", allow_empty=True) == ""
    assert sanitize_input("", allow_empty=False) is None

    # Test invalid input (characters not in whitelist)
    assert sanitize_input("ls | grep test") is None  # pipe not allowed
    assert sanitize_input("echo $HOME") is None  # dollar sign not allowed
    assert sanitize_input("echo `ls`") is None  # backtick not allowed

    print("✓ sanitize_input tests passed")


def test_safe_shell_split():
    """Test safe shell splitting."""
    # Test valid command
    assert safe_shell_split("ls -la") == ["ls", "-la"]
    assert safe_shell_split('echo "hello world"') == ["echo", "hello world"]

    # Test invalid quoting
    assert safe_shell_split('echo "unclosed quote') is None

    # Test pipe - shlex.split will split it into tokens, so we get a list (not None)
    # Note: pipe character is treated as a regular argument when shell=False
    assert safe_shell_split("ls | grep test") == ['ls', '|', 'grep', 'test']

    # Test empty/whitespace
    assert safe_shell_split("") is None
    assert safe_shell_split("   ") is None

    print("✓ safe_shell_split tests passed")


if __name__ == "__main__":
    test_sanitize_input()
    test_safe_shell_split()
    print("All input validator tests passed!")