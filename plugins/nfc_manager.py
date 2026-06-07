import shutil
from core.jailbreak import safe_exec


_NFC_STATUS = None


def _check_nfc():
    global _NFC_STATUS
    if _NFC_STATUS is not None:
        return _NFC_STATUS

    r = safe_exec("launchctl list | grep nfcd", timeout=5)
    nfcd_running = r["success"]

    patches = [
        ("/usr/lib/NFCD", "nfcd patch"),
        ("/Library/MobileSubstrate/DynamicLibraries/NFCD.dylib", "NFCWriter"),
    ]
    found_patch = any(__import__('os').path.exists(p) for p, _ in patches)

    if nfcd_running and found_patch:
        _NFC_STATUS = "patched"
    elif nfcd_running:
        _NFC_STATUS = "running"
    else:
        _NFC_STATUS = "unavailable"

    return _NFC_STATUS


def nfc_manager(args=""):
    status = _check_nfc()

    lines = ["[NFC]"]

    if status == "unavailable":
        lines.append("  iPhone 6s NFC is locked to Apple Pay.")
        lines.append("  Requires nfcd patch (e.g. NFCWriter XS from Sileo)")
        lines.append("  for third-party tag reading/writing.")
        return "\n".join(lines)

    if status == "running":
        lines.append("  nfcd running but no NFC patch detected.")
        lines.append("  Install NFCWriter XS for tag support.")
        return "\n".join(lines)

    parts = args.strip().split(None, 1)
    cmd = parts[0].lower() if parts else "scan"
    data = parts[1] if len(parts) > 1 else ""

    if cmd == "scan":
        lines.append("  Scanning for NFC tag...")
        r = safe_exec("rc nfc scan", timeout=10)
        if r["success"]:
            lines.append(f"  Tag: {r['stdout'].strip()}")
        else:
            lines.append("  No tag found.")
    elif cmd == "write" and data:
        lines.append(f'  Writing: "{data}"')
        r = safe_exec(f"rc nfc write {__import__('shlex').quote(data)}", timeout=10)
        if r["success"]:
            lines.append(f"  OK: {r['stdout'].strip()}")
        else:
            lines.append("  Write failed.")
    else:
        lines.append("  Usage: nfc_manager [scan|write <data>]")

    return "\n".join(lines)


SKILL = {
    "name": "nfc_manager",
    "description": "NFC tag scan/write — requires NFCWriter XS patch (iPhone 6s NFC locked to Apple Pay without it)",
    "run": nfc_manager,
}
