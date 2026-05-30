import subprocess
import os
import urllib.parse


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

    def run(self, cmd, timeout=30):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "TIMEOUT", "code": -1}
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
