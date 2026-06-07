import re
import shutil
from core.jailbreak import safe_exec


def _ioreg_display():
    """Read display info via ioreg (requires IOKitTools)."""
    if not shutil.which("ioreg"):
        return None
    data = {}
    paths = [
        ["-rc", "AppleBacklightDisplay"],
        ["-p", "IODeviceTree", "-r", "-n", "display"],
        ["-rc", "AppleCLCD"],
    ]
    for args in paths:
        try:
            r = safe_exec("ioreg " + " ".join(args), timeout=8)
            if not r["success"] or not r["stdout"].strip():
                continue
            out = r["stdout"]
            def _get(k):
                m = re.search(rf'"{k}"\s*=\s*(\S+)', out)
                return m.group(1).rstrip(",") if m else None
            for key in ("brightness", "IOMirror", "IOFramebuffer", "display-type", "resolution"):
                v = _get(key)
                if v is not None:
                    data[key.lower().replace("-", "_")] = v
            m = re.search(r'(\d+)x(\d+)', out)
            if m:
                data["resolution"] = f"{m.group(1)}x{m.group(2)}"
        except Exception:
            pass
    if not data:
        return None
    return data


def _sysctl_display():
    """Fallback: basic display info via sysctl."""
    try:
        r = safe_exec("sysctl -n hw.memsize", timeout=5)
        data = {}
        for key in ("hw.pagesize", "kern.bootargs"):
            r2 = safe_exec(f"sysctl -n {key}", timeout=5)
            if r2["success"] and r2["stdout"].strip():
                data[key.split(".")[-1]] = r2["stdout"].strip()[:60]
        return data if data else None
    except Exception:
        return None


def run_display(args=""):
    data = _ioreg_display()
    lines = []
    if data:
        lines.append("Display:")
        if "brightness" in data:
            lines.append(f"  Brightness: {data['brightness']}")
        if "resolution" in data:
            lines.append(f"  Resolution: {data['resolution']}")
        for k, v in data.items():
            if k not in ("brightness", "resolution"):
                lines.append(f"  {k}: {v}")
    else:
        fallback = _sysctl_display()
        if shutil.which("ioreg"):
            lines.append("Display info unavailable (ioreg found no display service)")
        else:
            lines.append("Display info unavailable — install IOKitTools via Sileo")
        if fallback:
            lines.append("sysctl:")
            for k, v in fallback.items():
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


SKILL = {
    "name": "display",
    "description": "Display info — brightness, resolution (needs IOKitTools for most data)",
    "run": run_display,
}
