import subprocess
import shutil
import glob
import os


HAPTIC_SOUNDS = [
    "/System/Library/Audio/UISounds/nano/3rd_error_2.caf",
    "/System/Library/Audio/UISounds/nano/3rd_error_1.caf",
    "/System/Library/Audio/UISounds/nano/3rd_prompt.caf",
    "/System/Library/Audio/UISounds/Tock.caf",
    "/System/Library/Audio/UISounds/click.caf",
    "/System/Library/Audio/UISounds/lock.caf",
]


def _find_haptic_cafs():
    found = []
    for pattern in [
        "/System/Library/Audio/UISounds/nano/*.caf",
        "/System/Library/Audio/UISounds/*.caf",
    ]:
        for f in sorted(glob.glob(pattern)):
            name = os.path.basename(f).replace(".caf", "")
            found.append((name, f))
            if len(found) >= 10:
                break
        if found:
            break
    return found


def _play_sound(path):
    if not shutil.which("afplay"):
        return False, "afplay not available"
    try:
        r = subprocess.run(
            ["afplay", path],
            capture_output=True, timeout=5
        )
        return r.returncode == 0, ""
    except Exception as e:
        return False, str(e)


def run_vibrate(args=""):
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "list":
        sounds = _find_haptic_cafs()
        if not sounds:
            return "No haptic audio files found on this device"
        lines = ["Available haptic sounds:"]
        for name, path in sounds:
            lines.append(f"  {name}")
        return "\n".join(lines)

    if subcmd:
        sound_file = None
        for pattern in [
            f"/System/Library/Audio/UISounds/nano/{subcmd}.caf",
            f"/System/Library/Audio/UISounds/{subcmd}.caf",
            subcmd,
        ]:
            if os.path.exists(pattern):
                sound_file = pattern
                break
        if not sound_file:
            return (f"Sound '{subcmd}' not found. Use @plugin vibrate list "
                    "to see available sounds")
        ok, err = _play_sound(sound_file)
        return f"Playing {subcmd}..." if ok else f"Failed: {err}"

    if shutil.which("afplay"):
        for snd in HAPTIC_SOUNDS:
            if os.path.exists(snd):
                ok, _ = _play_sound(snd)
                return "Vibrate (haptic audio played)" if ok else "Failed to play haptic"
        return ("No haptic audio files found — try @plugin vibrate list "
                "or use Sileo to install haptic bundles")
    return "Vibrate not available (afplay not found)"


SKILL = {
    "name": "vibrate",
    "description": "Haptic feedback — @plugin vibrate [sound|list] (plays haptic audio via afplay)",
    "run": run_vibrate,
}
