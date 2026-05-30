import re

MAX_CMD_LEN = 500

BLOCKED = [
    # Root/system destruction
    (r'\brm\s+-rf\s+/\s*$', "rm -rf /"),
    (r'\brm\s+-rf\s+/\s+\S', "rm -rf / with args"),
    (r'\brm\s+-rf\s+\~/?\s*$', "rm -rf ~ (home)"),
    (r'\brm\s+-rf\s+\$HOME', "rm -rf \$HOME"),
    (r'\brm\s+-rf\s+/\*', "rm -rf /* (glob root)"),
    # Disk/block device operations
    (r'\bdd\s+if=.*of=/dev/', "dd to raw device"),
    (r'\bmkfs\.\w+\s+/dev/', "mkfs on device"),
    (r'\bfdisk\s+/dev/', "fdisk on device"),
    (r'>\s*/dev/[hs]d', "write to block device"),
    (r'>\s*/dev/r?\w+', "write to /dev/ device"),
    # Privilege escalation
    (r'\bchmod\s+777\s+/', "chmod 777 /"),
    (r'\bchown\s+-R\s+\S+\s+/\s*$', "chown -R /"),
    (r'\bsu\s+[-\s]', "switch user"),
    (r'\bsudo\s+', "sudo (not available)"),
    (r'\bpasswd\s+', "change password"),
    (r'\bchroot\s+', "chroot"),
    # System shutdown/reboot
    (r'\bshutdown\s+-[rhPH]', "shutdown/reboot"),
    (r'\breboot\s*$', "reboot"),
    (r'\bpoweroff\s*$', "poweroff"),
    (r'\bhalt\s*$', "halt"),
    (r'\binit\s+[06]\b', "init 0/6 (shutdown)"),
    # Fork bomb
    (r':\(\)\s*\{', "fork bomb"),
    # Remote code execution patterns
    (r'(curl|wget)\s+.*\|\s*(?:sh|bash|zsh|python|python3|perl|ruby)', "pipe download to shell"),
    (r'(curl|wget)\s+.*-O\s+.*&&\s*(?:sh|bash|python|python3|perl|ruby)', "download and execute"),
    (r'`.*(?:rm|dd|mkfs|reboot|shutdown|chmod|chown|passwd|su|sudo).*?`', "backtick with dangerous cmd"),
    (r'\$\s*\((?:rm|dd|mkfs|reboot|shutdown|chmod|chown|passwd|su|sudo)', "subshell with dangerous cmd"),
    (r'\$\(.*\)', "subshell execution (blocked)"),
    (r'`.*`', "backtick execution (blocked)"),
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
    r'\buser(del|mod)\s+',
    r'\bpasswd\s+',
    r'\bsudo\s+',
]

CONFIRM_CMD = input if __name__ != "__main__" else input
_proactive_yes = False


def check(cmd):
    """Returns (blocked_reason, is_destructive)"""
    if len(cmd) > MAX_CMD_LEN:
        return (f"[BLOCKED] Command exceeds {MAX_CMD_LEN} chars ({len(cmd)})", False)

    for pat, reason in BLOCKED:
        if re.search(pat, cmd, re.IGNORECASE):
            return (f"[BLOCKED] {reason}", False)
    is_dest = any(re.search(p, cmd, re.IGNORECASE) for p in DESTRUCTIVE)
    return (None, is_dest)


def check_ai_response(text):
    """Pre-check AI response for dangerous commands before execution"""
    dangerous_keywords = ["rm -rf", "dd if=", ":(){", "mkfs.", "reboot", "poweroff", "halt"]
    for match in re.finditer(r'@cmd\s+(.+)', text):
        cmd = match.group(1).strip()
        for kw in dangerous_keywords:
            if kw in cmd.lower():
                return f"AI response blocked: contains '{kw}'"
    return None


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
