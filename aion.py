#!/usr/bin/env python3
"""AION-6S: AI Operating Layer for Jailbroken iPhone 6s"""

import os
import sys
import json
import re
import gc
import time
try:
    import fcntl
except ImportError:
    fcntl = None
import copy
import itertools
import threading
try:
    import readline
except ImportError:
    pass


ANSI = {
    "AI": "\033[94m",
    "SYS": "\033[92m",
    "ERR": "\033[91m",
    "WARN": "\033[93m",
    "CMD": "\033[95m",
    "GRY": "\033[90m",
    "DIM": "\033[2m",
    "BOLD": "\033[1m",
    "RST": "\033[0m",
    "CLR": "\033[2J\033[H",
}

MODES = {
    "chat": "Chat with AI. Commands execute; destructive ops ask confirmation.",
    "plan": "AI plans only. Commands are listed — nothing executes.",
    "build": "Plan → execute step by step with confirmation.",
    "auto": "Full autonomous. Everything executes, guardrails still block nukes.",
}

AUDIT_LOG = os.path.join(os.path.dirname(__file__), "aion-audit.log")


def c(color, text):
    sys.stdout.write(f"{ANSI[color]}{text}{ANSI['RST']}")
    sys.stdout.flush()


def cl(color, text):
    print(f"{ANSI[color]}{text}{ANSI['RST']}")


def _obfuscate_secrets(text):
    """Obfuscate sensitive data like API keys in text."""
    if not isinstance(text, str):
        return text
    # Obfuscate NVIDIA API keys
    text = re.sub(r'nvapi-[A-Za-z0-9\-_]{20,}', 'nvapi-[REDACTED]', text)
    # Obfuscate other potential secrets
    text = re.sub(r'sk-[A-Za-z0-9]{20,}', 'sk-[REDACTED]', text)
    text = re.sub(r'ghp_[A-Za-z0-9]{20,}', 'ghp_[REDACTED]', text)
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED_EMAIL]', text)
    return text

def audit_log(entry):
    """Thread-safe audit logging with file locking and secret obfuscation."""
    try:
        # Create a copy of entry to avoid modifying original
        entry_copy = copy.deepcopy(entry)

        # Obfuscate secrets in the entry
        def obfuscate_dict(d):
            if isinstance(d, dict):
                for key, value in d.items():
                    if isinstance(value, str):
                        d[key] = _obfuscate_secrets(value)
                    elif isinstance(value, dict):
                        obfuscate_dict(value)
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, str):
                                value[i] = _obfuscate_secrets(item)
                            elif isinstance(item, dict):
                                obfuscate_dict(item)
            elif isinstance(d, list):
                for i, item in enumerate(d):
                    if isinstance(item, str):
                        d[i] = _obfuscate_secrets(item)
                    elif isinstance(item, dict):
                        obfuscate_dict(item)
                    elif isinstance(item, list):
                        for j, subitem in enumerate(item):
                            if isinstance(subitem, str):
                                item[j] = _obfuscate_secrets(subitem)

        obfuscate_dict(entry_copy)

        with open(AUDIT_LOG, "a") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry_copy) + "\n")
            finally:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass  # Fail gracefully on iOS filesystem restrictions


SESSION_DIR = os.path.join(os.path.dirname(__file__), "sessions")

PIXEL_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹⠸⠼⠳⠦⠧⠇⠏"


class AION:
    __slots__ = [
        "config", "bridge", "jailbreak", "memory",
        "healer", "plugins", "system_prompt", "mode",
        "config_path", "cmd_history", "last_user_msg",
        "workspace",
    ]

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.config = self._load_or_create_config()
        self.mode = "chat"
        self.cmd_history = []
        self.last_user_msg = ""
        # Define workspace directory for sandboxing
        self.workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
        os.makedirs(self.workspace, exist_ok=True)
        self._init_components()

    def _validate_config(self, config):
        """Validate and sanitize config values"""
        # Type checking and bounds
        if not isinstance(config.get("max_context_pairs"), int) or config["max_context_pairs"] < 1:
            config["max_context_pairs"] = 5
        if config["max_context_pairs"] > 20:
            config["max_context_pairs"] = 20  # Hard limit for iPhone

        if not isinstance(config.get("max_tokens"), int) or config["max_tokens"] < 100:
            config["max_tokens"] = 512
        if config["max_tokens"] > 4096:
            config["max_tokens"] = 4096  # API limit

        if not isinstance(config.get("max_heal_attempts"), int) or config["max_heal_attempts"] < 0:
            config["max_heal_attempts"] = 3
        if config["max_heal_attempts"] > 10:
            config["max_heal_attempts"] = 10

        if "temperature" in config:
            temp = config.get("temperature", 0.7)
            if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                config["temperature"] = 0.7

        if config.get("jailbreak_mode") not in ("auto", "newterm", "ashell"):
            config["jailbreak_mode"] = "auto"

        tout = config.get("request_timeout", 90)
        if not isinstance(tout, (int, float)) or tout < 15:
            config["request_timeout"] = 90
        if tout > 180:
            config["request_timeout"] = 180

        rl = config.get("rate_limit", 30)
        if not isinstance(rl, int) or rl < 1:
            config["rate_limit"] = 30
        if rl > 120:
            config["rate_limit"] = 120

        # Validate base_url to prevent SSRF
        if "base_url" in config:
            url = config["base_url"]
            if not isinstance(url, str) or not url.startswith("https://"):
                config["base_url"] = "https://integrate.api.nvidia.com/v1"
            elif "integrate.api.nvidia.com" not in url and "api.anthropic.com" not in url:
                cl("WARN", f"  [SECURITY] Unusual base_url: {url[:50]}")

        return config

    def _load_or_create_config(self):
        default_config = {
            "api_key": "",
            "model": "deepseek-ai/deepseek-v4-flash",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "jailbreak_mode": "auto",
            "max_context_pairs": 5,
            "max_heal_attempts": 3,
            "temperature": 0.7,
            "max_tokens": 512,
            "request_timeout": 90,
            "rate_limit": 30
        }

        # Prefer environment variable for API key (more secure)
        if os.environ.get("NVIDIA_API_KEY"):
            default_config["api_key"] = os.environ["NVIDIA_API_KEY"]
            # Skip file based config if env var is set
            return default_config

        while True:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path) as f:
                        config = json.load(f)
                    config = self._validate_config(config)
                    key = config.get("api_key", "")
                    if not key or len(key) < 40 or key == "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":
                        config["api_key"] = self._prompt_api_key()
                        self._save_config(config)
                    return config
                except Exception as e:
                    cl("ERR", f"Config load error: {e}")
            cl("SYS", "No valid config found. Please configure AION-6S.")
            config = self._validate_config(self._prompt_config_interactive(default_config))
            if config.get("api_key"):
                return config

    def _prompt_api_key(self):
        sys.stdout.write(f"{ANSI['SYS']}Enter NVIDIA API key (nvapi-xxx): {ANSI['RST']}")
        sys.stdout.flush()
        try:
            key = input().strip()
            if key and key.startswith("nvapi-"):
                return key
            cl("ERR", "Invalid key format. Must start with 'nvapi-'")
        except EOFError:
            pass
        return ""

    def _prompt_config_interactive(self, default_config):
        c("SYS", "Enter API key: ")
        try:
            key = input().strip()
        except EOFError:
            key = ""

        config = default_config.copy()
        config["api_key"] = key if key.startswith("nvapi-") else ""
        self._save_config(config)
        return config

    def _save_config(self, config):
        """Atomic config save with file locking."""
        tmp_path = self.config_path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(config, f, indent=2)
                finally:
                    if fcntl:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.replace(tmp_path, self.config_path)
        except Exception as e:
            cl("ERR", f"Config save error: {e}")

    def _init_components(self):
        from core.bridge import Bridge
        from core.jailbreak import Jailbreak
        from core.memory import MemoryManager
        from core.self_heal import SelfHeal
        from core.guardrails import check, confirm, reset_confirm
        from plugins import load_plugins

        self._check_config_security()

        self.bridge = Bridge(self.config)
        self.jailbreak = Jailbreak(self.config.get("jailbreak_mode", "auto"), workspace=self.workspace)
        self.memory = MemoryManager(self.config.get("max_context_pairs", 5))
        self.healer = SelfHeal(self.bridge, self.config.get("max_heal_attempts", 3))
        self.plugins = load_plugins(os.path.join(os.path.dirname(__file__), "plugins"))
        self.system_prompt = self._build_prompt()
        self.memory.set_system(self.system_prompt)

    def _check_config_security(self):
        if os.environ.get("NVIDIA_API_KEY"):
            return
        if os.path.exists(self.config_path):
            mode = oct(os.stat(self.config_path).st_mode)[-3:]
            if mode != "600" and mode != "640":
                cl("WARN", f"  [SECURITY] config.json permissions: {mode} (recommend: 600)")
        if self.config.get("api_key"):
            cl("WARN", "  [SECURITY] API key stored in plaintext config.json")
            cl("WARN", "  [SECURITY] Safer: set NVIDIA_API_KEY env var instead")

    def _build_prompt(self):
        plugin_list = "\n".join(
            f"  @plugin {k} - {v['description']}"
            for k, v in self.plugins.items()
        ) or "  (none)"
        return f"""You are AION-6S on a jailbroken iPhone 6s (2GB RAM, a-Shell/NewTerm).

AVAILABLE NÁSTROJE:
{plugin_list}
  @cmd <shell command>     - execute system command
  @shortcut run <name> [input]  - run iOS Shortcut
  @shortcut create <name>       - create new iOS Shortcut
  @shortcut list                - list all iOS Shortcuts

JAK POUŽÍVAT NÁSTROJE:
Když uživatel požádá o něco co vyžaduje nástroj, postupuj takto:

1. NAPIŠ nástroj (např. @plugin battery nebo @cmd pmset -g batt)
2. POČKEJ — systém nástroj spustí, výsledek uvidíš
3. DEJ FINÁLNÍ ODPOVĚĎ na základě výsledku

Příklad:
  Uživatel: "dej mi baterku"
  Ty: @plugin battery
  [systém spustí, ty uvidíš: "Battery: 85%, discharging"]
  Ty: "Máš 85% baterky, telefon se vybíjí, vydrží asi 3 hodiny."

MODES (user switches with /plan, /build, /auto, /chat):
  plan  — you list the steps, user reviews before any execute
  build — you propose steps, user confirms one by one
  auto  — you execute immediately, guardrails block destruction
  chat  — normal chat, commands execute with warnings

SECURITY RULES (strictly follow):
- NEVER generate @cmd with: rm -rf, dd, mkfs, reboot, poweroff, halt, chroot, sudo.
- NEVER pipe downloads (curl/wget) directly to shell (sh, bash, python).
- NEVER use backticks or $() with dangerous commands.
- When in doubt, suggest a safe alternative and ask the user.
- Commands over 500 characters are blocked.

RULES:
- Be concise in final answers.
- When a command fails, analyze the error and suggest a fix.
- Memory is tight (2GB) — keep responses short.
- In /plan mode: output numbered steps using @cmd, they won't run.
- In /build mode: output @cmd and explain each step."""

    def _exec_cmd(self, cmd, allow_heal=True):
        from core.guardrails import check, confirm, reset_confirm

        t0 = time.time()

        blocked, is_dest = check(cmd)
        if blocked:
            c("ERR", f"  ✗ $ {cmd}")
            print(f"{ANSI['GRY']}  │{ANSI['RST']} {blocked}")
            audit_log({"t": time.time(), "action": "blocked", "cmd": cmd, "reason": blocked})
            return None

        if self.mode == "plan":
            c("GRY", f"  [plan] $ {cmd}")
            print()
            return None

        if self.mode in ("chat", "build") and is_dest:
            cl("WARN", f"  [DANGEROUS] $ {cmd}")
            if not confirm(cmd):
                cl("WARN", "  Skipped.")
                audit_log({"t": time.time(), "action": "skipped", "cmd": cmd, "reason": "user declined"})
                return None

        self.cmd_history.append(cmd)
        if len(self.cmd_history) > 100:
            self.cmd_history = self.cmd_history[-50:]

        c("GRY", f"  ◎ $ {cmd}")
        result = self.jailbreak.run(cmd)

        duration = time.time() - t0

        ok = result and result.get("success")
        sys.stdout.write(f"  {ANSI['SYS'] if ok else ANSI['ERR']}{'✓' if ok else '✗'}{ANSI['RST']} ({duration:.1f}s)\n")

        if result and result["stdout"]:
            for line in result["stdout"].rstrip().split("\n"):
                print(f"{ANSI['GRY']}  │{ANSI['RST']} {line}")
        if result and result["stderr"]:
            for line in result["stderr"].rstrip().split("\n"):
                print(f"{ANSI['GRY']}  │{ANSI['RST']} {ANSI['ERR']}{line}{ANSI['RST']}")

        if result and not result["success"] and result["stderr"] and allow_heal:
            c("WARN", "  \u21bb healing...")
            fix = self.healer.heal(cmd, result["stderr"])
            if fix and fix != cmd:
                blocked2, _ = check(fix)
                if not blocked2:
                    c("GRY", f"  ◎ $ {fix}")
                    healed = self.jailbreak.run(fix)
                    dur2 = time.time() - t0
                    if healed and healed["success"]:
                        sys.stdout.write(f"  {ANSI['SYS']}✓{ANSI['RST']} ({dur2:.1f}s)\n")
                        result = healed
                        if healed.get("stdout"):
                            for line in healed["stdout"].rstrip().split("\n"):
                                print(f"{ANSI['GRY']}  │{ANSI['RST']} {line}")
                    else:
                        sys.stdout.write(f"  {ANSI['ERR']}✗{ANSI['RST']} ({dur2:.1f}s)\n")
                        if healed and healed.get("stderr"):
                            for line in healed["stderr"].rstrip().split("\n"):
                                print(f"{ANSI['GRY']}  │{ANSI['RST']} {ANSI['ERR']}{line}{ANSI['RST']}")

        success = result.get("success", False) if result else False
        audit_log({
            "t": time.time(), "action": "exec",
            "cmd": cmd, "mode": self.mode,
            "success": success, "duration": round(duration, 2),
        })

        return result

    def _exec_plugin(self, name, args=""):
        if name not in self.plugins:
            c("ERR", f"  ✗ @plugin {name} {args} — not found")
            msg = f"Plugin '{name}' not found. Available: {list(self.plugins.keys())}"
            return {"success": False, "output": msg}
        t0 = time.time()
        c("GRY", f"  ◎ @plugin {name} {args}")
        try:
            output = self.plugins[name]["run"](args)
            dur = time.time() - t0
            sys.stdout.write(f"  {ANSI['SYS']}✓{ANSI['RST']} ({dur:.1f}s)\n")
            if output:
                for line in output.strip().split("\n"):
                    print(f"{ANSI['GRY']}  │{ANSI['RST']} {line}")
            return {"success": True, "output": output or ""}
        except Exception as e:
            dur = time.time() - t0
            sys.stdout.write(f"  {ANSI['ERR']}✗{ANSI['RST']} ({dur:.1f}s)\n")
            msg = f"Plugin error: {e}"
            print(f"{ANSI['GRY']}  │{ANSI['RST']} {msg}")
            return {"success": False, "output": msg}

    def _exec_shortcut(self, text):
        from core.input_validator import safe_shell_split
        parts = safe_shell_split(text)
        if not parts:
            cl("ERR", "  [shortcut] missing arguments")
            return {"success": False, "stdout": "", "stderr": "missing arguments", "code": -1}
        action = parts[0]
        name = parts[1] if len(parts) > 1 else None
        inp = parts[2] if len(parts) > 2 else None
        cl("SYS", f"  [shortcut] {action} {name or ''}")
        return self.jailbreak.run_shortcut(action, name, inp)

    def _process_ai_response(self, text, heal=True):
        from core.guardrails import check_ai_response
        blocked = check_ai_response(text)
        if blocked:
            cl("ERR", f"  {blocked}")
            audit_log({"t": time.time(), "action": "ai_blocked", "reason": blocked})
            return []

        results = []
        for match in re.finditer(r'@(cmd|plugin|shortcut)\s+(.+)', text, re.MULTILINE):
            kind = match.group(1)
            rest = match.group(2).strip().strip('"').strip("'")
            result = {"kind": kind, "input": rest, "stdout": "", "success": False}
            if kind == "cmd":
                cmd_res = self._exec_cmd(rest, allow_heal=heal)
                if cmd_res:
                    result["stdout"] = (cmd_res.get("stdout") or "") + (cmd_res.get("stderr") or "")
                    result["success"] = cmd_res.get("success", False)
                    result["exit_code"] = cmd_res.get("exit_code", 0)
            elif kind == "plugin":
                parts = rest.split(None, 1)
                plugin_res = self._exec_plugin(parts[0], parts[1] if len(parts) > 1 else "")
                result["stdout"] = plugin_res["output"]
                result["success"] = plugin_res["success"]
            elif kind == "shortcut":
                shortcut_res = self._exec_shortcut(rest)
                result["success"] = shortcut_res.get("success", True) if shortcut_res else True
                result["stdout"] = (shortcut_res.get("stdout") or "") + (shortcut_res.get("stderr") or "") if shortcut_res else ""
            results.append(result)
        return results

    def _format_tool_results(self, results):
        lines = []
        for r in results:
            kind = r["kind"]
            inp = r["input"]
            if kind == "cmd":
                status = "OK" if r["success"] else f"FAILED (exit {r.get('exit_code', '?')})"
                lines.append(f"[cmd] $ {inp}  [{status}]")
                out = (r.get("stdout") or "").rstrip()
                if out:
                    lines.append(out[:2000])
            elif kind == "plugin":
                lines.append(f"[plugin] {inp}")
                out = (r.get("stdout") or "").rstrip()
                if out:
                    lines.append(out[:2000])
            elif kind == "shortcut":
                lines.append(f"[shortcut] {inp}")
        result = "\n".join(lines)
        return result[:5000] if len(result) > 5000 else result

    def _handle_special(self, line):
        from core.guardrails import reset_confirm

        cmd = line.strip().lower()

        if cmd.startswith("/mode ") or cmd in ("/plan", "/build", "/auto", "/chat"):
            mode = cmd.split()[-1] if " " in cmd else cmd[1:]
            if mode in MODES:
                self.mode = mode
                reset_confirm()
                cl("SYS", f"Mode → {mode}")
                cl("SYS", f"  {MODES[mode]}")
            else:
                cl("ERR", f"Unknown mode. Available: {list(MODES.keys())}")

        elif cmd == "/log":
            if os.path.exists(AUDIT_LOG):
                with open(AUDIT_LOG) as f:
                    lines = f.readlines()
                last = lines[-min(len(lines), 15):]
                cl("SYS", f"Last {len(last)} audit entries:")
                for l in last:
                    try:
                        e = json.loads(l)
                        ts = time.strftime("%H:%M:%S", time.localtime(e["t"]))
                        cl("SYS", f"  {ts} {e.get('action','?'):>8} | {e.get('cmd','')[:50]}")
                    except Exception:
                        pass
            else:
                cl("SYS", "No audit log yet.")

        elif cmd == "/plugins":
            cl("SYS", f"Plugins ({len(self.plugins)}):")
            for k, v in self.plugins.items():
                cl("SYS", f"  {k}: {v['description']}")

        elif cmd == "/clear":
            self.memory.set_system(self.system_prompt)
            cl("SYS", "Context cleared.")

        elif cmd == "/retry":
            last = None
            for msg in reversed(self.memory.get_context()):
                if msg["role"] == "user":
                    last = msg["content"]
                    break
            if not last:
                cl("ERR", "No previous query to retry.")
                return
            ctx = self.memory.get_context()
            last_idx = None
            for i in range(len(ctx) - 1, -1, -1):
                if ctx[i]["role"] == "user":
                    last_idx = i
                    break
            if last_idx is not None:
                self.memory.context = ctx[:last_idx + 1]
            cl("SYS", "Retrying last query...")
            resp = self._stream(gray=False)
            if resp is None:
                for attempt in range(3):
                    cl("WARN", f"  API error — retrying (attempt {attempt+2}/4)…")
                    resp = self._stream(gray=False)
                    if resp is not None:
                        break
                if resp is None:
                    cl("ERR", "  All retries failed — try again later")
                    return
            print()
            final = resp
            if self.mode != "plan":
                for rnd in range(5):
                    results = self._process_ai_response(final, heal=False)
                    if not results:
                        break
                    self.memory.add("tool", self._format_tool_results(results))
                    nxt = self._stream(gray=False)
                    if nxt is None:
                        break
                    final = nxt
            prompt_chars = sum(len(m.get("content", "")) for m in self.memory.get_context())
            self._show_stats(prompt_chars, len(final))
            self.memory.add("assistant", final)
            self.memory.cleanup()

        elif cmd == "/battery":
            self._exec_plugin("battery", "")

        elif line.lower().startswith("/apikey"):
            parts = line.split(None, 1)
            if len(parts) == 1:
                key = self.config.get("api_key", "")
                masked = key[:12] + "..." + key[-4:] if len(key) > 16 else "(not set)"
                cl("SYS", f"API key: {masked}")
                cl("SYS", "Usage: /apikey nvapi-xxxxxxxxxxxx")
            else:
                new_key = parts[1].strip()
                self.config["api_key"] = new_key
                self._save_config(self.config)
                self.bridge.update_config(self.config)
                cl("SYS", "API key updated")

        elif cmd == "/heal":
            cl("SYS", self.healer.summary())

        elif cmd == "/info":
            info = self.jailbreak.info()
            cl("SYS", f"Mode: {self.mode}  |  Jailbreak: {info['mode']}")
            cl("SYS", f"OS: {info['uname'][:80]}")

        elif cmd == "/help":
            cl("SYS", f"""Commands:
  /plan              Plan mode — AI plans, nothing executes
  /build             Build mode — execute with step confirmation
  /auto              Auto mode — full autonomous, guardrails only
  /chat              Chat mode (default) — commands with warning
  /battery           Check battery status
  /apikey <key>      Change API key
  /plugins           List loaded plugins
  /model [name]      Show/change model (no args = list available)
  /clear             Reset conversation context
  /heal              Show self-healing history
  /retry             Retry last query
  /info              System info
  /save [name]       Save session
  /load [name]       Load session
  /reload            Reload plugins
  /status            System status
  /log               Show last audit log entries
  /update            Download latest files from GitHub
  !! / !N            Repeat last / Nth command
  /help              This message""")
        elif cmd == "/reload":
            from plugins import reload_plugins
            self.plugins = reload_plugins(os.path.join(os.path.dirname(__file__), "plugins"))
            self.system_prompt = self._build_prompt()
            cl("SYS", f"Plugins reloaded. {len(self.plugins)} active.")

        elif cmd == "/update":
            cl("SYS", "Updating AION-6S from GitHub...")
            files = [
                "aion.py", "config.example.json",
                "core/__init__.py", "core/bridge.py", "core/jailbreak.py",
                "core/memory.py", "core/guardrails.py", "core/self_heal.py",
                "core/input_validator.py",
                "plugins/__init__.py", "plugins/system_tools.py", "plugins/nfc_manager.py",
                "plugins/battery.py", "plugins/location.py", "plugins/webfetch.py",
                "plugins/weather.py",
            ]
            base_url = "https://raw.githubusercontent.com/hulskero/aion-6s/main/"
            import subprocess
            for f in files:
                cl("SYS", f"  {f}")
                r = subprocess.run(
                    ["curl", "-sL", base_url + f, "-o", f],
                    timeout=30
                )
                if r.returncode != 0:
                    cl("ERR", f"  failed: {f}")
            cl("SYS", "Update done. Restart with: python3 aion.py")
            sys.exit(0)

        elif cmd == "/status":
            import time
            ctx = self.memory.get_context()
            chars = sum(len(m.get("content", "")) for m in ctx)
            cl("SYS", f"Mode: {self.mode}")
            cl("SYS", f"Context: {len(ctx)} msgs, ~{chars} chars")
            cl("SYS", f"Cmd history: {len(self.cmd_history)} entries")
            cl("SYS", f"Model: {self.config['model']}")
            if hasattr(self.bridge, '_last_latency'):
                cl("SYS", f"Last API latency: {self.bridge._last_latency:.1f}s")

        elif cmd.startswith("/save"):
            parts = cmd.split(None, 1)
            name = parts[1].strip() if len(parts) > 1 else "default"
            if not os.path.isdir(SESSION_DIR):
                os.makedirs(SESSION_DIR)
            path = os.path.join(SESSION_DIR, f"{name}.json")
            data = {
                "mode": self.mode,
                "config": self.config,
                "context": self.memory.get_context(),
                "cmd_history": self.cmd_history[-20:],
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            cl("SYS", f"Session saved: {name}")

        elif cmd.startswith("/load"):
            parts = cmd.split(None, 1)
            name = parts[1].strip() if len(parts) > 1 else "default"
            path = os.path.join(SESSION_DIR, f"{name}.json")
            if not os.path.exists(path):
                cl("ERR", f"Session '{name}' not found.")
                return
            with open(path) as f:
                data = json.load(f)
            self.mode = data.get("mode", "chat")
            self.memory.set_system(self.system_prompt)
            for msg in data.get("context", []):
                if msg["role"] != "system":
                    self.memory.add(msg["role"], msg["content"])
            self.cmd_history = data.get("cmd_history", [])
            cl("SYS", f"Session loaded: {name} ({len(data.get('context',[]))} msgs)")

        elif cmd.startswith("/model"):
            parts = cmd.split(None, 1)
            if len(parts) == 1:
                # List available models
                cl("SYS", "Available NVIDIA models:")
                cl("SYS", "  deepseek-ai/deepseek-v4-flash  - Balanced (default)")
                cl("SYS", "  deepseek-ai/deepseek-v4        - Full version")
                cl("SYS", "  nvidia/llama-3.1-nemotron-70b  - Large")
                cl("SYS", f"Current: {self.config['model']}")
            else:
                # Change model
                new_model = parts[1].strip()
                valid_models = ["deepseek-ai/deepseek-v4-flash", "deepseek-ai/deepseek-v4", "nvidia/llama-3.1-nemotron-70b"]
                if new_model in valid_models:
                    self.config["model"] = new_model
                    self._save_config(self.config)
                    self.bridge.update_config(self.config)
                    cl("SYS", f"Model → {new_model}")
                else:
                    cl("ERR", f"Unknown model. Use /model to list available.")
        else:
            cl("ERR", f"Unknown: {cmd}")

    def _stream(self, label="AI", gray=False):
        """Stream AI response with animated braille spinner + elapsed time."""
        stop = threading.Event()
        t0 = time.time()
        def spin():
            for char in itertools.cycle(PIXEL_SPINNER):
                if stop.is_set():
                    return
                elapsed = time.time() - t0
                sys.stdout.write(f"\r\033[K{ANSI['WARN']}{char}{ANSI['RST']} Working... ({elapsed:.0f}s)")
                sys.stdout.flush()
                time.sleep(0.08)
        t = threading.Thread(target=spin, daemon=True)
        t.start()

        color = ANSI["GRY"] if gray else ANSI[label]
        text = ""
        try:
            for token in self.bridge.stream(self.memory.get_context()):
                if not stop.is_set():
                    stop.set()
                    t.join()
                    sys.stdout.write(f"\r\033[K{color}{label}>{ANSI['RST']} ")
                sys.stdout.write(f"{color}{token}{ANSI['RST']}")
                sys.stdout.flush()
                text += token
        except Exception as e:
            if not stop.is_set():
                stop.set()
                t.join()
            cl("ERR", f"\n[API Error] {e}")
            return None
        return text

    def _show_stats(self, prompt_chars, completion_chars):
        usage = self.bridge.get_usage()
        if usage:
            prompt = usage.get("prompt_tokens", prompt_chars)
            completion = usage.get("completion_tokens", completion_chars)
        else:
            prompt = f"{prompt_chars}c"
            completion = f"{completion_chars}c"
        latency = getattr(self.bridge, "_last_latency", 0)
        cl("SYS", f"  ↑{prompt} ↓{completion} | {latency:.1f}s | {self.config['model']}")

    def run(self):
        MAX_TOOL_ROUNDS = 5
        cl("SYS", f"{ANSI['BOLD']}AION-6S{ANSI['RST']} ready  |  {len(self.plugins)} plugin(s)  |  {self.config['model']}")
        cl("SYS", f"Mode: {self.mode}  |  Type /help for commands.")

        while True:
            try:
                line = input(f"{ANSI['WARN']}{self.mode}>{ANSI['RST']} ")
            except (EOFError, KeyboardInterrupt):
                cl("SYS", "\nBye.")
                break

            raw = line.strip()
            if not raw:
                continue

            if raw == "!!":
                if self.cmd_history:
                    raw = self.cmd_history[-1]
                    cl("SYS", f"Repeating: {ANSI['CMD']}{raw}{ANSI['RST']}")
                else:
                    cl("ERR", "No commands in history.")
                    continue
            elif raw.startswith("!") and raw[1:].isdigit():
                idx = int(raw[1:])
                if 1 <= idx <= len(self.cmd_history):
                    raw = self.cmd_history[idx - 1]
                    cl("SYS", f"Repeating #{idx}: {ANSI['CMD']}{raw}{ANSI['RST']}")
                else:
                    cl("ERR", f"No command #{idx} in history ({len(self.cmd_history)} total).")
                    continue

            line = raw

            if line.startswith("/"):
                self._handle_special(line)
                continue

            self.memory.add("user", line)

            response = self._stream(gray=False)
            if response is None:
                for attempt in range(3):
                    cl("WARN", f"  API error — retrying (attempt {attempt+2}/4)…")
                    response = self._stream(gray=False)
                    if response is not None:
                        break
                if response is None:
                    cl("ERR", "  All retries failed — /retry or try again later")
                    continue
            final = response

            if self.mode != "plan":
                for rnd in range(MAX_TOOL_ROUNDS):
                    results = self._process_ai_response(final, heal=False)
                    if not results:
                        break

                    c("DIM", f"\n  \u2501 round {rnd+1}/{MAX_TOOL_ROUNDS} \u2501\n")

                    self.memory.add("tool", self._format_tool_results(results))

                    next_resp = self._stream(gray=False)
                    if next_resp is None:
                        cl("WARN", "  API error — /retry the last query")
                        break
                    final = next_resp
            else:
                self._process_ai_response(response, heal=False)

            prompt_chars = sum(len(m.get("content", "")) for m in self.memory.get_context())
            self._show_stats(prompt_chars, len(final))
            self.memory.add("assistant", final)
            self.memory.cleanup()


if __name__ == "__main__":
    AION().run()
