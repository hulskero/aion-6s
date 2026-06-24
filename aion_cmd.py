#!/usr/bin/env python3
"""aion_cmd.py — Run a single AION-6S command and print output.
Patches subprocess to use /var/jb/bin/sh when /bin/sh doesn't exist.
Set AION_HEADLESS=1 to suppress security warnings.
"""
import os, sys, json, subprocess

os.environ["AION_HEADLESS"] = "1"

# If NVIDIA_API_KEY not in env, try config.json (legacy) then encrypted keyring
if not os.environ.get("NVIDIA_API_KEY"):
    _base = os.path.dirname(os.path.abspath(__file__))
    # Try plaintext config.json first (legacy)
    try:
        with open(os.path.join(_base, "config.json")) as _cf:
            _cfg = json.load(_cf)
        _key = _cfg.get("api_key", "")
        if _key:
            os.environ["NVIDIA_API_KEY"] = _key
    except (OSError, ValueError):
        pass
    # Try encrypted config.key
    if not os.environ.get("NVIDIA_API_KEY"):
        try:
            sys.path.insert(0, _base)
            from core.keyring import load_key, key_exists
            _key_path = os.path.join(_base, "config.key")
            if key_exists(_key_path):
                _pw = os.environ.get("AION_KEY_PASSPHRASE", "testpass123")
                _key = load_key(_key_path, _pw)
                if _key:
                    os.environ["NVIDIA_API_KEY"] = _key
        except Exception:
            pass

_orig_init = subprocess.Popen.__init__
def _patched_init(self, args, bufsize=-1, executable=None, **kwargs):
    if executable is None and kwargs.get('shell') and not os.path.exists('/bin/sh'):
        executable = '/var/jb/bin/sh'
    _orig_init(self, args, bufsize=bufsize, executable=executable, **kwargs)
subprocess.Popen.__init__ = _patched_init

os.environ["PATH"] = "/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", "")

AION_DIR = "/var/mobile/Documents/aion-6s"
os.chdir(AION_DIR)
sys.path.insert(0, AION_DIR)
sys.stdin = open("/dev/null", "r")

from aion import AION

agent = AION()

SOCK_PATH = "/tmp/aion-daemon.sock"
_use_daemon = os.path.exists(SOCK_PATH)

if len(sys.argv) < 2:
    if _use_daemon:
        import subprocess as _sp
        r = _sp.run(["python3", os.path.join(AION_DIR, "aion_dclient.py"), "--wait"],
                     capture_output=True, text=True, timeout=35)
        print(r.stdout)
    else:
        agent.run()
    sys.exit(0)

line = sys.argv[1].strip()
if not line:
    sys.exit(0)

# Use daemon if available
if _use_daemon:
    import subprocess as _sp
    r = _sp.run(["python3", os.path.join(AION_DIR, "aion_dclient.py"), line],
                 capture_output=True, text=True, timeout=120)
    if r.stdout:
        print(r.stdout.strip())
    sys.exit(r.returncode)

# Fallback: direct execution
if line.startswith("/"):
    agent._handle_special(line)
elif line.startswith("!"):
    cmd = line[1:].strip()
    if cmd:
        r = agent.jailbreak.run(cmd, timeout=15)
        agent._print_output(r)
elif line.startswith("@read "):
    path = line[len("@read "):].strip()
    result = agent._read_file(path)
    print(result)
elif line.startswith("@grep "):
    result = agent._grep_search(line[len("@grep "):].strip())
    print(result)
elif line.startswith("@glob "):
    result = agent._glob_search(line[len("@glob "):].strip())
    print(result)
else:
    agent.memory.add("user", line)
    response = agent._stream(gray=False)
    if response:
        print(response)
    else:
        sys.exit(1)

