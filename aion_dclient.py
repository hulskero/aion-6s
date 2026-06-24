#!/usr/bin/env python3
"""aion_dclient.py — Send command to AION daemon via Unix socket.
Usage:
  python3 aion_dclient.py /battery
  python3 aion_dclient.py "what is 2+2?"
  python3 aion_dclient.py --wait   # wait for daemon to start
"""
import json, socket, sys, time, os

SOCK_PATH = "/tmp/aion-daemon.sock"

def send(cmd, timeout=30):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(SOCK_PATH)
    sock.sendall(cmd.encode("utf-8"))
    data = b""
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    sock.close()
    return json.loads(data.decode("utf-8"))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: aion_dclient.py <command>")
        sys.exit(1)

    if sys.argv[1] == "--wait":
        _, resp = None, None
        for i in range(30):
            if os.path.exists(SOCK_PATH):
                try:
                    resp = send("/sysinfo", timeout=2)
                    if resp.get("exitCode") == 0:
                        print("Daemon ready")
                        sys.exit(0)
                except:
                    pass
            time.sleep(1)
        print("Daemon not ready after 30s")
        sys.exit(1)

    cmd = " ".join(sys.argv[1:])
    try:
        result = send(cmd, timeout=60)
        out = result.get("output", "")
        if out:
            print(out)
        sys.exit(result.get("exitCode", 1))
    except Exception as e:
        print(f"Daemon error: {e}", file=sys.stderr)
        sys.exit(1)
