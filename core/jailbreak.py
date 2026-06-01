import subprocess
import os
import glob as globmod
import urllib.parse

from core.input_validator import safe_shell_split

# Simple shell tokenizer for iOS commands
# Maps common commands to safe handlers
SAFE_COMMANDS = {
    # System info — a-Shell compatible
    'uname': None, 'df': None, 'hostname': None, 'id': None,
    'whoami': None, 'pwd': None, 'date': None, 'uptime': None,
    'sysctl': None, 'vm_stat': None,
    # Hardware / IOKit
    'ioreg': None, 'pmset': None,
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
    # Audio / haptics
    'afplay': None,
    # Scripting
    'python3': None, 'python': None, 'printenv': None, 'env': None,
    # Editors
    'vim': None, 'pico': None, 'ed': None, 'nano': None,
    # Process
    'ps': None, 'kill': None, 'pkill': None, 'killall': None,
    # Disk
    'mount': None, 'stat': None, 'du': None,
    # Package management (Procursus)
    'apt': None, 'apt-get': None, 'dpkg': None,
    # Source control / download
    'git': None, 'wget': None, 'rsync': None, 'curl': None,
    # Archive
    'unzip': None, 'tar': None, 'gzip': None, 'bzip2': None,
    # Launch / service
    'launchctl': None,
    # NFC / RemoteCompanion
    'rc': None,
}


def _split_pipeline(cmd):
    """Split command on | outside quotes. Returns list of command strings."""
    parts = []
    current = []
    in_sq = False
    in_dq = False
    for char in cmd:
        if char == "'" and not in_dq:
            in_sq = not in_sq
        elif char == '"' and not in_sq:
            in_dq = not in_dq
        elif char == '|' and not in_sq and not in_dq:
            parts.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append(''.join(current).strip())
    return [p for p in parts if p]


def _has_glob(pattern):
    """Check if a string contains unquoted glob characters."""
    in_sq = False
    in_dq = False
    for char in pattern:
        if char == "'" and not in_dq:
            in_sq = not in_sq
        elif char == '"' and not in_sq:
            in_dq = not in_dq
        if not in_sq and not in_dq and char in ('*', '?', '['):
            return True
    return False


def _expand_glob_args(argv):
    """Expand glob patterns in argv list. Non-matching globs pass through literally."""
    expanded = []
    for arg in argv:
        if _has_glob(arg):
            matches = sorted(globmod.glob(arg))
            if matches:
                expanded.extend(matches)
            else:
                expanded.append(arg)
        else:
            expanded.append(arg)
    return expanded


def _tokenize(cmd):
    """Parse command into safe argv list. Returns None if potentially unsafe."""
    parts = safe_shell_split(cmd)
    if not parts:
        return None

    cmd_name = os.path.basename(parts[0])

    # Allow known safe commands
    if cmd_name in SAFE_COMMANDS:
        return parts

    # Command not in SAFE_COMMANDS whitelist
    return None


# Module-level cached Jailbreak instance for plugins
_SYSTEM_JB = None


def safe_exec(cmd, timeout=30):
    """Central safe execution for plugins. Same security as Jailbreak.run().
    Use this instead of raw subprocess.run() in plugin code."""
    global _SYSTEM_JB
    if _SYSTEM_JB is None:
        _SYSTEM_JB = Jailbreak(timeout=timeout)
    return _SYSTEM_JB.run(cmd)


class Jailbreak:
    __slots__ = ["mode", "workspace", "timeout"]

    def __init__(self, mode="auto", workspace=None, timeout=30):
        self.mode = self._detect(mode)
        self.workspace = workspace
        self.timeout = timeout

    def _detect(self, mode):
        if mode != "auto":
            return mode
        if os.path.exists("/var/mobile"):
            self._fix_path()
            return "newterm"
        if os.path.exists("/Library"):
            return "ashell"
        return "ashell"

    @staticmethod
    def _fix_path():
        jb_bin = "/var/jb/usr/bin"
        if os.path.isdir(jb_bin) and jb_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{jb_bin}:{os.environ.get('PATH', '')}"

    @staticmethod
    def _expand_subshells(cmd):
        """Replace $(cmd) with its output. Handles nesting via recursion."""
        import re as _re
        pattern = r'\$\(([^()]+|(?:[^()]*\([^()]*\)[^()]*)*)\)'
        while True:
            m = _re.search(pattern, cmd)
            if not m:
                break
            inner = m.group(1)
            r = safe_exec(inner.strip(), timeout=15)
            replacement = r["stdout"].strip() if r["success"] else ""
            cmd = cmd[:m.start()] + replacement + cmd[m.end():]
        return cmd

    def run(self, cmd, timeout=None):
        """Execute command safely. Handles pipes, globs, subshells, always uses argv (shell=False).
        Default timeout from config, overridable per-call."""
        if timeout is None:
            timeout = self.timeout
        cmd = self._expand_subshells(cmd)
        pipeline = _split_pipeline(cmd)
        if len(pipeline) > 1:
            return self._run_pipeline(pipeline, timeout)

        argv = _tokenize(cmd)
        if argv is None:
            cmd_name = cmd.strip().split()[0] if cmd.strip() else "?"
            return {"success": False, "stdout": "", "stderr": f"Command not allowed: '{cmd_name}'. Check SAFE_COMMANDS or use @plugin.", "code": -1}
        argv = _expand_glob_args(argv)
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

    def _run_pipeline(self, segments, timeout):
        """Run a pipeline of commands connected by pipes. No shell=True needed."""
        tokenized = []
        for seg in segments:
            argv = _tokenize(seg)
            if argv is None:
                cmd_name = seg.strip().split()[0] if seg.strip() else "?"
                return {"success": False, "stdout": "", "stderr": f"Command not allowed in pipeline: '{cmd_name}'", "code": -1}
            argv = _expand_glob_args(argv)
            tokenized.append(argv)

        try:
            procs = []
            prev = None
            for argv in tokenized:
                kwargs = dict(
                    args=argv,
                    shell=False,
                    stdin=subprocess.PIPE if prev is None else prev.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.workspace,
                )
                p = subprocess.Popen(**kwargs)
                if prev:
                    prev.stdout.close()
                procs.append(p)
                prev = p

            stdout, stderr = procs[-1].communicate(timeout=timeout)
            rc = procs[-1].returncode
            return {
                "success": rc == 0,
                "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
                "code": rc,
            }
        except subprocess.TimeoutExpired:
            for p in procs:
                p.kill()
            return {"success": False, "stdout": "", "stderr": "TIMEOUT", "code": -1}
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
