#!/usr/bin/env python3
"""Network status plugin: IP address, DNS resolution test"""
import subprocess, socket


def run(args=""):
    try:
        # Get IP address
        ip = "n/a"
        try:
            r = subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True, timeout=5)
            ip = r.stdout.strip() or "n/a"
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            pass

        # Test DNS resolution
        dns_ok = "?"
        socket.setdefaulttimeout(3)
        try:
            socket.getaddrinfo("google.com", 80)
            dns_ok = "OK"
        except (socket.gaierror, socket.timeout, OSError):
            dns_ok = "FAIL"

        # Get BSSID from summary
        bssid = "n/a"
        try:
            r = subprocess.run(["ipconfig", "getsummary", "en0"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split("\n"):
                if "BSSID" in line:
                    bssid = line.split(":")[-1].strip()
                    if bssid:
                        break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            pass

        return f"IP: {ip}  |  BSSID: {bssid}  |  DNS: {dns_ok}"
    except Exception as e:
        return f"Network error: {e}"


SKILL = {"name": "net", "description": "IP address, Wi-Fi BSSID, DNS connectivity", "run": run}
