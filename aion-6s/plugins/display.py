import shutil
from core.jailbreak import safe_exec
from core.ios_hw import ioreg_get_first, ioreg_get_properties, get_display_specs


def run_display(args=""):
    props = ioreg_get_first("AppleCLCD")
    if not props:
        props = ioreg_get_first("AppleMobileADBE0")

    lines = ["Display:"]

    if props:
        res = None
        for k in ('IODisplayEDID', 'EDID', 'IOModuleIdentifier'):
            v = props.get(k)
            if v and isinstance(v, (bytes, bytearray)):
                edid = v if isinstance(v, bytes) else bytes(v)
                if len(edid) >= 72:
                    w = edid[56] | ((edid[58] & 0xF0) << 4)
                    h = edid[59] | ((edid[61] & 0xF0) << 4)
                    if w and h:
                        res = f"{w}x{h}"
                        break

        if not res:
            fb = props.get('IOFramebuffer')
            if fb and isinstance(fb, dict):
                w, h = fb.get('w'), fb.get('h')
                if w and h:
                    res = f"{w}x{h}"

        if not res:
            rows = props.get('displayPixelRows')
            cols = props.get('displayPixelColumns')
            if rows is not None and cols is not None:
                res = f"{cols}x{rows}"

        if res:
            lines.append(f"  Resolution: {res}")

        brightness = props.get('brightness')
        if brightness is None:
            pm = props.get('IOPowerManagement')
            if isinstance(pm, dict):
                brightness = pm.get('CurrentPowerState')
        if brightness is not None:
            lines.append(f"  Brightness: {brightness}")

    if not props:
        specs = get_display_specs()
        if specs:
            lines.append(f"  Resolution: {specs['w']}x{specs['h']} (hardcoded, {specs.get('name', '?')})")
            lines.append(f"  PPI: {specs['ppi']}  Scale: {specs.get('scale', 1)}x")
        else:
            r = safe_exec("ioreg -rc AppleCLCD -w 0", timeout=5)
            if r["success"] and r["stdout"].strip():
                lines.append("  (data available via ioreg install)")
            else:
                lines.append("  Resolution: unknown device")

    return "\n".join(lines)


SKILL = {
    "name": "display",
    "description": "Display info — brightness, resolution (needs IOKitTools for most data)",
    "run": run_display,
}
