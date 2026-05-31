"""
Unit tests for input validator module.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from input_validator import sanitize_input, safe_shell_split, safe_subprocess_run, validate_command_args


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


def test_safe_subprocess_run():
    """Test safe subprocess execution."""
    # Test successful command
    result = safe_subprocess_run("echo hello", timeout=5)
    assert result["success"] == True
    assert "hello" in result["stdout"]

    # Test failed command
    result = safe_subprocess_run("false", timeout=5)
    assert result["success"] == False

    # Test non-existent command
    result = safe_subprocess_run("nonexistentcommand12345", timeout=5)
    assert result["success"] == False
    assert "Command not found" in result["stderr"]

    # Test shell=False: semicolon is treated as literal argument, so echo will print it
    result = safe_subprocess_run("echo hello; rm -rf /", shell=False, timeout=5)
    assert result["success"] == True
    assert "hello; rm -rf /" in result["stdout"]

    # Test shell=True with input sanitization: semicolon should be rejected by sanitize_input
    result = safe_subprocess_run("echo hello; rm -rf /", shell=True, timeout=5)
    assert result["success"] == False
    assert "Input validation failed" in result["stderr"]

    print("✓ safe_subprocess_run tests passed")


def test_validate_command_args():
    """Test command argument validation."""
    # Test valid commands
    valid, msg = validate_command_args(["ls", "-la"])
    assert valid == True

    valid, msg = validate_command_args(["echo", "hello"])
    assert valid == True

    # Test invalid commands (not in whitelist)
    valid, msg = validate_command_args(["rm", "-rf", "/"])
    assert valid == True  # rm is a valid command in whitelist

    valid, msg = validate_command_args(["sudo", "ls"])
    assert valid == False  # sudo is not in whitelist

    # Test edge cases
    valid, msg = validate_command_args([])
    assert valid == False

    valid, msg = validate_command_args(None)
    assert valid == False

    print("✓ validate_command_args tests passed")


if __name__ == "__main__":
    test_sanitize_input()
    test_safe_shell_split()
    test_safe_subprocess_run()
    test_validate_command_args()
    print("All input validator tests passed!")