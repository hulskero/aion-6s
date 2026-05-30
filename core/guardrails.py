import re

BLOCKED = [
    (r'\brm\s+-rf\s+/\s*$', "rm -rf / — nuking the system"),
    (r'\brm\s+-rf\s+/\s+\w', "rm -rf / — nuking the system"),
    (r'\bdd\s+if=.*\s+of=/dev/', "dd writing to raw device"),
    (r':\(\)\s*\{', "fork bomb"),
    (r'\bmkfs\..*\s+/dev/', "mkfs on a device"),
    (r'\bfdisk\s+/dev/', "fdisk on a device"),
    (r'\bchmod\s+777\s+/', "chmod 777 /"),
    (r'\bchown\s+-R\s+.*\s+/$', "chown -R /"),
    (r'>\s*/dev/[hs]d', "write to raw block device"),
    (r'\bshutdown\s+-[rhPH]', "system shutdown/reboot"),
    (r'\breboot\s*$', "reboot"),
    (r'\bpoweroff\s*$', "poweroff"),
    (r'\bhalt\s*$', "halt"),
]

DESTRUCTIVE = [
    r'\brm\s+',
    r'\bmv\s+',
    r'\bdd\s+',
    r'\bkill\s+\d+',
    r'\bpkill\s+\w+',
    r'>\s+\S+',
    r'>>\s+\S+',
    r'\bchmod\s+',
    r'\bchown\s+',
    r'\bapt(-get)?\s+(remove|purge|autoremove)',
    r'\bdpkg\s+-[rP]',
    r'\bsystemctl\s+(stop|disable|mask)',
    r'\blaunchctl\s+unload',
    r'\bpasswd\s+',
    r'\buser(del|mod)\s+',
]

CONFIRM_CMD = input if __name__ != "__main__" else input
_proactive_yes = False


def check(cmd):
    """Returns (blocked_reason, is_destructive)"""
    for pat, reason in BLOCKED:
        if re.search(pat, cmd):
            return (f"[BLOCKED] {reason}", False)
    is_dest = any(re.search(p, cmd) for p in DESTRUCTIVE)
    return (None, is_dest)


def confirm(cmd):
    global _proactive_yes
    if _proactive_yes:
        return True
    r = input(f"  \033[93mDestructive. Execute? (y/n/\033[1ma\033[22mlways\033[93m) \033[0m")
    if r.lower() == "a":
        _proactive_yes = True
        return True
    return r.lower() == "y"


def reset_confirm():
    global _proactive_yes
    _proactive_yes = False
