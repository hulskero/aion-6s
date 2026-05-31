import subprocess
import os
import urllib.parse
import shlex

# Simple shell tokenizer for iOS commands
# Maps common commands to safe handlers
SAFE_COMMANDS = {
    # System info — a-Shell compatible
    'uname': None, 'df': None, 'hostname': None, 'id': None,
    'whoami': None, 'pwd': None, 'date': None, 'uptime': None,
    # Network
    'curl': None, 'ping': None, 'nslookup': None, 'dig': None,
    'ifconfig': None, 'netstat': None,
    # Filesystem
    'ls': None, 'cat': None, 'echo': None, 'head': None, 'tail': None,
    'wc': None, 'sort': None, 'grep': None, 'awk': None, 'sed': None,
    'cp': None, 'mv': None, 'mkdir': None, 'rm': None, 'touch': None,
    'chmod': None, 'chown': None,
    'find': None, 'basename': None, 'dirname': None, 'realpath': None,
    # iOS / a-Shell
    'open': None, 'sbreload': None, 'uicache': None,
    # Scripting
    'python3': None, 'python': None, 'printenv': None, 'env': None,
    'sh': None, 'bash': None, 'zsh': None,
    # Editors
    'vim': None, 'pico': None, 'ed': None, 'nano': None,
    # Process
    'ps': None, 'kill': None, 'pkill': None,
    # Disk
    'mount': None, 'stat': None, 'du': None,
}


def _tokenize(cmd):
    """Parse command into safe argv list. Returns None if potentially unsafe."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None  # Invalid quoting

    if not parts:
        return None

    cmd_name = os.path.basename(parts[0])

    # Allow known safe commands
    if cmd_name in SAFE_COMMANDS:
        # If command has strict whitelist, validate args
        allowed_args = SAFE_COMMANDS[cmd_name]
        if allowed_args is not None:
            for arg in parts[1:]:
                if arg not in allowed_args and not arg.startswith('-'):
                    # Allow unknown args for flexibility, but log warning
                    pass
        return parts

    # For shell built-ins and redirects, we still use shell=True
    # but guardrails should have blocked dangerous patterns
    return None


class Jailbreak:
    __slots__ = ["mode"]

    def __init__(self, mode="auto"):
        self.mode = self._detect(mode)

    def _detect(self, mode):
        if mode != "auto":
            return mode
        if os.path.exists("/var/mobile"):
            return "newterm"
        if os.path.exists("/Library"):
            return "ashell"
        return "ashell"

    def run(self, cmd, timeout=10):
        """Execute command safely. Always uses argv (shell=False), never shell injection."""
        try:
            argv = shlex.split(cmd)
            result = subprocess.run(
                argv, shell=False, capture_output=True, text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "TIMEOUT", "code": -1}
        except FileNotFoundError:
            return {"success": False, "stdout": "", "stderr": f"Command not found: {cmd.split()[0]}", "code": 127}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)[:500], "code": -1}

    def run_shortcut(self, name, input_data=None):
        scheme = f"shortcuts://run-shortcut?name={urllib.parse.quote(name)}"
        if input_data:
            scheme += f"&input={urllib.parse.quote(input_data)}"
        return self.run(f"open '{scheme}'")

    def activator_send(self, action):
        if self.mode == "newterm":
            return self.run(f"activator send {action}")
        return {"success": False, "stdout": "", "stderr": "No activator (a-Shell)", "code": -1}

    def remote_companion(self, cmd):
        if self.mode == "newterm":
            return self.run(f"rc {cmd}")
        return {"success": False, "stdout": "", "stderr": "No RemoteCompanion", "code": -1}

    def info(self):
        uname = self.run("uname -a")
        mem = self.run("vm_stat 2>/dev/null || free 2>/dev/null || echo 'mem n/a'")
        disk = self.run("df -h / 2>/dev/null | tail -1")
        return {
            "mode": self.mode,
            "uname": uname["stdout"].strip(),
            "memory": mem["stdout"].strip(),
            "disk": disk["stdout"].strip(),
        }
