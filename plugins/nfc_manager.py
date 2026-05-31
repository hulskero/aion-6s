import subprocess
import os


def nfc_scan(args=""):
    lines = ["[NFC] Attempting tag scan..."]

    if os.path.exists("/usr/bin/rc"):
        try:
            r = subprocess.run(["rc", "nfc", "scan"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                lines.append(f"  rc: {r.stdout.strip()}")
                return "\n".join(lines)
            lines.append(f"  rc failed: {r.stderr.strip()}")
        except Exception as e:
            lines.append(f"  rc error: {e}")

    lines.append("  Opening Shortcuts NFC scanner (if configured)...")
    subprocess.run(
        ["open", "shortcuts://run-shortcut?name=ScanNFC"],
        capture_output=True, timeout=5
    )

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


def nfc_manager(args=""):
    """Unified NFC plugin - handles scan and write subcommands"""
    parts = args.strip().split(None, 1)
    command = (parts[0] if parts else "scan").lower()
    data = parts[1] if len(parts) > 1 else ""

    if command == "scan":
        return nfc_scan()
    elif command == "write":
        return nfc_write(data)
    else:
        return "[NFC] Usage: @plugin nfc_manager [scan|write \"data\"]\n  scan - Scan for NFC tag\n  write \"data\" - Write data to NFC tag"


SKILL = {
    "name": "nfc_manager",
    "description": "Scan and write NFC tags via jailbreak tools (rc) or Shortcuts fallback",
    "run": nfc_manager,
}
