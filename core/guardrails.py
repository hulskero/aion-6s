import re

MAX_CMD_LEN = 500
# Version: 2026-05-31-1 - Enhanced guardrails for AION-6S

# Extended list of blocked patterns with more comprehensive protection
BLOCKED = [
    # Root/system destruction
    (r'\brm\s+-rf\s+/\s*$', "rm -rf /"),
    (r'\brm\s+-rf\s+/\s+\S', "rm -rf / with args"),
    (r'\brm\s+-rf\s+\~/?\s*$', "rm -rf ~ (home)"),
    (r'\brm\s+-rf\s+\$HOME', "rm -rf $HOME"),
    (r'\brm\s+-rf\s+/\*', "rm -rf /* (glob root)"),
    # (catch-all rm -rf removed — workspace sandbox handles safety)

    # Disk/block device operations
    (r'\bdd\s+if=.*of=/dev/', "dd to raw device"),
    (r'\bmkfs\.\w+\s+/dev/', "mkfs on device"),
    (r'\bfdisk\s+/dev/', "fdisk on device"),
    (r'>\s*/dev/[hs]d', "write to block device"),
    (r'>\s*/dev/r?\w+', "write to /dev/ device"),
    (r'dd\s+if=.*of=.*\|\s*.*', "dd pipe to another command"),

    # Privilege escalation
    (r'\bchmod\s+[7-9]{3}\s+/', "chmod with dangerous permissions on root"),
    (r'\bchown\s+-R\s+\S+\s+/\s*$', "chown -R /"),
    (r'\bsu\s+[-\s]', "switch user"),
    (r'\bsudo\s+', "sudo (not available)"),
    (r'\bpasswd\s+', "change password"),
    (r'\bchroot\s+', "chroot"),
    (r'\busermod\s+', "modify user accounts"),
    (r'\buseradd\s+', "add user accounts"),
    (r'\buserdel\s+', "delete user accounts"),

    # System shutdown/reboot
    (r'\bshutdown\s+', "shutdown command"),
    (r'\breboot\s+', "reboot command"),
    (r'\bpoweroff\s+', "poweroff command"),
    (r'\bhalt\s+', "halt command"),
    (r'\binit\s+[06]', "init 0/6 (shutdown)"),
    (r'\bsystemctl\s+(poweroff|reboot|halt)', "systemctl power operations"),

    # Fork bomb and similar
    (r':\(\)\s*\{', "fork bomb"),
    (r'\[.*\]\s*-\s*\[.*\]\s*&\s*while\s+true', "another fork bomb variant"),

    # Remote code execution patterns
    (r'(curl|wget|fetch)\s+.*\|\s*(?:sh|bash|zsh|python|python3|perl|ruby|ash|dash)', "pipe download to shell"),
    (r'(curl|wget|fetch)\s+.*-O\s+.*\&\&.*\s*(?:sh|bash|zsh|python|python3|perl|ruby|ash|dash)', "download and execute"),
    (r'(curl|wget|fetch)\s+.*\&\&.*\s*(?:sh|bash|zsh|python|python3|perl|ruby|ash|dash)', "download then execute"),
    (r'`.*(?:rm|dd|mkfs|reboot|shutdown|chmod|chown|passwd|su|sudo|chroot|mount|umount).*?`', "backtick with dangerous cmd"),
    (r'\$\s*\((?:rm|dd|mkfs|reboot|shutdown|chmod|chown|passwd|su|sudo|chroot|mount|umount)', "subshell with dangerous cmd"),
    # $(...) handled safely by jailbreak._expand_subshells — no longer blocked here
    (r'`.*`', "backtick execution (blocked)"),

    # File system damage - protected directories
    (r'>\s*/etc/', "writing to /etc directory"),
    (r'>\s*/boot/', "writing to /boot directory"),
    (r'>\s*/bin/', "writing to /bin directory"),
    (r'>\s*/sbin/', "writing to /sbin directory"),
    (r'>\s*/usr/bin/', "writing to /usr/bin directory"),
    (r'>\s*/usr/sbin/', "writing to /usr/sbin directory"),
    (r'>>\s*/etc/', "appending to /etc directory"),
    (r'>\s*/var/', "writing to /var directory"),
    (r'>>\s*/var/', "appending to /var directory"),
    (r'>\s*/Users/.*/Library/', "writing to user Library directory"),
    (r'>>\s*/Users/.*/Library/', "appending to user Library directory"),
    (r'>\s*/private/etc/', "writing to /private/etc directory"),
    (r'>\s*/private/var/', "writing to /private/var directory"),
    (r'mv\s+/etc/.*', "moving /etc files"),
    (r'mv\s+/var/.*', "moving /var files"),
    (r'mv\s+/Users/.*/Library/.*', "moving user Library files"),
    (r'cp\s+/etc/.*', "copying /etc files"),
    (r'cp\s+/var/.*', "copying /var files"),
    (r'cp\s+/Users/.*/Library/.*', "copying user Library files"),

    # Dangerous mounts
    (r'mount\s+.*\/\s*', "remounting root"),
    (r'umount\s+\/\s*', "unmounting root"),
    (r'mount\s+.*\s+/\s*', "mounting to root"),

    # Module/driver manipulation
    (r'insmod\s+', "insert kernel module"),
    (r'rmmod\s+', "remove kernel module"),
    (r'modprobe\s+', "load kernel module"),

    # Network manipulation that could be dangerous
    (r'iptables\s+.*\-P\s+.*(DROP|ACCEPT)', "iptables policy change"),
    (r'ifconfig\s+.*down', "network interface down"),
    (r'ip\s+link\s+set\s+.*down', "ip link set down"),
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
    r'\bchroot\s+',
    r'\bshutdown\s+',
    r'\breboot\s+',
    r'\bpoweroff\s+',
    r'\bhalt\s+',
    r'\binit\s+',
    r'\bmkfs\s+',
    r'\bfdisk\s+',
    r'\bparted\s+',
    r'\bpartprobe\s+',
    r'\bhdparm\s+',
    r'\bwipefs\s+',
    r'\bcryptsetup\s+',
    r'\blvm\s+',
    r'\bvg\s+',
    r'\blv\s+',
]

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
