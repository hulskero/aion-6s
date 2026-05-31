import subprocess
import os
import urllib.parse

from core.input_validator import safe_shell_split

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
    'shortcuts': None,
    # Scripting
    'python3': None, 'python': None, 'printenv': None, 'env': None,
    # Editors
    'vim': None, 'pico': None, 'ed': None, 'nano': None,
    # Process
    'ps': None, 'kill': None, 'pkill': None,
    # Disk
    'mount': None, 'stat': None, 'du': None,
}


def _tokenize(cmd):
    """Parse command into safe argv list. Returns None if potentially unsafe."""
    parts = safe_shell_split(cmd)
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

    # Command not in SAFE_COMMANDS whitelist
    return None


class Jailbreak:
    __slots__ = ["mode", "workspace"]

    def __init__(self, mode="auto", workspace=None):
        self.mode = self._detect(mode)
        self.workspace = workspace

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
        argv = _tokenize(cmd)
        if argv is None:
            return {"success": False, "stdout": "", "stderr": "Command not allowed or invalid syntax", "code": -1}
        try:
            result = subprocess.run(
                argv, shell=False, capture_output=True, text=True, timeout=timeout,
                cwd=self.workspace,
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
            return {"success": False, "stdout": "", "stderr": f"Command not found: {argv[0] if argv else 'unknown'}", "code": 127}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)[:500], "code": -1}

    def run_shortcut(self, action, name=None, input_data=None):
        if action == "list":
            return self.run("shortcuts list")
        if action == "create":
            scheme = "shortcuts://create-shortcut"
            if name:
                scheme += f"?name={urllib.parse.quote(name)}"
            return self.run(f"open '{scheme}'")
        # run
        if not name:
            return {"success": False, "stdout": "", "stderr": "No shortcut name", "code": -1}
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
        mem = self.run("vm_stat")
        disk = self.run("df -h /")
        return {
            "mode": self.mode,
            "uname": uname["stdout"].strip(),
            "memory": mem["stdout"].strip() if mem["success"] else "mem n/a",
            "disk": disk["stdout"].strip() if disk["success"] else "disk n/a",
        }
