import subprocess
import os


def nfc_scan(args=""):
    lines = []
    lines.append("[NFC] Attempting tag scan...")

    # 1) RemoteCompanion (jailbreak tweak)
    if os.path.exists("/usr/bin/rc"):
        try:
            r = subprocess.run(["rc", "nfc", "scan"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                lines.append(f"  rc: {r.stdout.strip()}")
                return "\n".join(lines)
            lines.append(f"  rc failed: {r.stderr.strip()}")
        except Exception as e:
            lines.append(f"  rc error: {e}")

    # 2) Shortcuts fallback
    lines.append("  Opening Shortcuts NFC scanner (if configured)...")
    try:
        subprocess.run(
            ["open", "shortcuts://run-shortcut?name=ScanNFC"],
            capture_output=True, timeout=5
        )
        lines.append("  Shortcut 'ScanNFC' launched.")
    except Exception as e:
        lines.append(f"  Shortcut failed: {e}")

    # 3) nfcd daemon check (jailbroken)
    if os.path.exists("/usr/libexec/nfcd"):
        lines.append("  nfcd present - NFC daemon available.")
    else:
        lines.append("  nfcd not found (non-jailbroken or no NFC support).")

    return "\n".join(lines)


def nfc_write(args=""):
    data = args.strip() or "Hello from AION-6S"
    lines = [f"[NFC] Writing tag: \"{data}\""]

    if os.path.exists("/usr/bin/rc"):
        try:
            r = subprocess.run(
                ["rc", "nfc", "write", data], capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                lines.append(f"  OK: {r.stdout.strip()}")
                return "\n".join(lines)
        except Exception as e:
            lines.append(f"  rc error: {e}")

    lines.append("  NFC write not available on this device.")
    return "\n".join(lines)


SKILL = {
    "name": "nfc_manager",
    "description": "Scan and write NFC tags via jailbreak tools (rc) or Shortcuts fallback",
    "run": nfc_scan,
}
