#!/usr/bin/env python3
"""aion_daemon.py — Persistent AION-6S daemon with Unix socket command interface.

Runs AION continuously in memory. Listens on /tmp/aion-daemon.sock for JSON
commands and returns responses — no Python startup overhead per call.
Managed by launchd via com.aion-6s.daemon.plist.

Usage:
  python3 aion_daemon.py              # start daemon (foreground)
  python3 aion_daemon.py --stop       # stop running daemon
  python3 aion_daemon.py --status     # check if running
"""
import os, sys, json, socket, threading, time, traceback

AION_DIR = "/var/mobile/Documents/aion-6s"
SOCK_PATH = "/tmp/aion-daemon.sock"
PID_PATH = "/tmp/aion-daemon.pid"

os.chdir(AION_DIR)
sys.path.insert(0, AION_DIR)

os.environ["AION_HEADLESS"] = "1"

# Kill stale daemon from previous pid file to prevent zombie pileup
if os.path.exists(PID_PATH):
    try:
        with open(PID_PATH) as _pf:
            _old_pid = int(_pf.read().strip())
        if _old_pid != os.getpid():
            os.kill(_old_pid, 15)
            time.sleep(0.2)
    except (ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.unlink(PID_PATH)
    except OSError:
        pass
if os.path.exists(SOCK_PATH):
    try:
        os.unlink(SOCK_PATH)
    except OSError:
        pass

# Load NVIDIA_API_KEY from config if not in env
if not os.environ.get("NVIDIA_API_KEY"):
    try:
        with open(os.path.join(os.path.dirname(__file__), "config.json")) as _cf:
            _cfg = json.load(_cf)
        _key = _cfg.get("api_key", "")
        if _key:
            os.environ["NVIDIA_API_KEY"] = _key
    except (OSError, ValueError):
        pass
os.environ["PATH"] = "/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", "")

# Monkey-patch subprocess for /var/jb/bin/sh
import subprocess as _sp
_orig_init = _sp.Popen.__init__
def _patched_init(self, args, bufsize=-1, executable=None, **kwargs):
    if executable is None and kwargs.get('shell') and not os.path.exists('/bin/sh'):
        executable = '/var/jb/bin/sh'
    _orig_init(self, args, bufsize=bufsize, executable=executable, **kwargs)
_sp.Popen.__init__ = _patched_init

from aion import AION


class AIONDaemon:
    def __init__(self):
        self.agent = AION()
        self._shutdown = threading.Event()

    def handle(self, cmd):
        """Process one command and return (output, exit_code)"""
        parts = cmd.split(" ", 1)
        prefix = parts[0] if len(parts) > 0 else ""
        rest = parts[1] if len(parts) > 1 else ""

        # Capture output
        from io import StringIO
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = buf = StringIO()
        sys.stderr = buf

        try:
            if cmd.startswith("/"):
                self.agent._handle_special(cmd)
            elif cmd.startswith("!"):
                subcmd = cmd[1:].strip()
                if subcmd:
                    r = self.agent.jailbreak.run(subcmd, timeout=15)
                    self.agent._print_output(r)
            elif cmd.startswith("@read "):
                path = cmd[len("@read "):].strip()
                result = self.agent._read_file(path)
                buf.write(str(result))
            elif cmd.startswith("@grep "):
                result = self.agent._grep_search(cmd[len("@grep "):].strip())
                buf.write(str(result))
            elif cmd.startswith("@glob "):
                result = self.agent._glob_search(cmd[len("@glob "):].strip())
                buf.write(str(result))
            else:
                self.agent.memory.add("user", cmd)
                response = self.agent._stream(gray=False)
                if response:
                    buf.write(response)
        except SystemExit:
            pass
        except Exception as e:
            buf.write(f"Error: {e}\n{traceback.format_exc()}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = buf.getvalue()
        # Strip ANSI codes for cleaner output
        import re
        output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
        output = re.sub(r'\x1b\][0-9;]*[^\x1b]*\x1b\\', '', output)
        output = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', output)
        exit_code = 0 if output.strip() else 1
        return output, exit_code

    def listen(self):
        """Start Unix socket listener"""
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(SOCK_PATH)
        sock.listen(5)
        os.chmod(SOCK_PATH, 0o777)

        with open(PID_PATH, "w") as f:
            f.write(str(os.getpid()))

        print(f"AION daemon ready on {SOCK_PATH} (pid={os.getpid()})")

        sock.settimeout(1.0)
        while not self._shutdown.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = conn.recv(65536)
                if not data:
                    conn.close()
                    continue
                cmd = data.decode("utf-8", errors="replace").strip()
                output, exit_code = self.handle(cmd)
                response = json.dumps({"exitCode": exit_code, "output": output})
                conn.sendall(response.encode("utf-8"))
            except Exception as e:
                try:
                    response = json.dumps({"exitCode": 1, "output": f"Daemon error: {e}"})
                    conn.sendall(response.encode("utf-8"))
                except (OSError, TypeError):
                    pass
            finally:
                conn.close()

        sock.close()
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        if os.path.exists(PID_PATH):
            os.unlink(PID_PATH)


def stop_daemon():
    if not os.path.exists(SOCK_PATH):
        print("Daemon not running")
        return
    import socket
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(SOCK_PATH)
        sock.sendall(b"__shutdown__")
        sock.close()
        print("Daemon stopped")
    except (OSError, socket.timeout):
        pass
    if os.path.exists(PID_PATH):
        with open(PID_PATH) as f:
            pid = f.read().strip()
        os.system(f"kill {pid} 2>/dev/null")
    for p in [SOCK_PATH, PID_PATH]:
        if os.path.exists(p):
            os.unlink(p)


def status():
    if os.path.exists(SOCK_PATH):
        import socket
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(SOCK_PATH)
            sock.sendall(b"/sysinfo")
            data = sock.recv(4096)
            sock.close()
            result = json.loads(data.decode())
            print(f"AION daemon RUNNING (pid={open(PID_PATH).read().strip() if os.path.exists(PID_PATH) else '?'})")
            print(f"  Last response: {result.get('output','')[:80]}")
        except (OSError, ValueError):
            print("AION daemon SOCKET EXISTS but not responding")
    else:
        print("AION daemon NOT RUNNING")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--stop":
            stop_daemon()
        elif sys.argv[1] == "--status":
            status()
        else:
            print(f"Usage: {sys.argv[0]} [--stop|--status]")
        sys.exit(0)

    daemon = AIONDaemon()
    daemon.listen()
