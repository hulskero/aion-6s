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


def audit_log(entry):
    """Thread-safe audit logging with file locking."""
    try:
        with open(AUDIT_LOG, "a") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
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
    ]

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.config = self._load_or_create_config()
        self.mode = "chat"
        self.cmd_history = []
        self.last_user_msg = ""
        self._init_components()

    def _validate_config(self, config):
        """Validate and sanitize config values"""
        # Type checking and bounds
        if not isinstance(config.get("max_context_pairs"), int) or config["max_context_pairs"] < 1:
            config["max_context_pairs"] = 5
        if config["max_context_pairs"] > 20:
            config["max_context_pairs"] = 20  # Hard limit for iPhone

        if not isinstance(config.get("max_tokens"), int) or config["max_tokens"] < 100:
            config["max_tokens"] = 2048
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

        tout = config.get("request_timeout", 120)
        if not isinstance(tout, (int, float)) or tout < 15:
            config["request_timeout"] = 120
        if tout > 300:
            config["request_timeout"] = 300

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
            "max_tokens": 2048,
            "request_timeout": 120,
            "rate_limit": 30
        }

        if os.environ.get("NVIDIA_API_KEY"):
            default_config["api_key"] = os.environ["NVIDIA_API_KEY"]
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
        self.jailbreak = Jailbreak(self.config.get("jailbreak_mode", "auto"))
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
  @shortcut <name> [input] - run iOS Shortcut

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
            cl("ERR", f"  {blocked}")
            audit_log({"t": time.time(), "action": "blocked", "cmd": cmd, "reason": blocked})
            return None

        if self.mode == "plan":
            cl("WARN", f"  [PLAN] Would run: $ {cmd}")
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

        cl("CMD", f"\n  $ {cmd}")
        result = self.jailbreak.run(cmd)

        duration = time.time() - t0

        if result and result["stdout"]:
            print(result["stdout"].rstrip())
        if result and result["stderr"]:
            cl("ERR", result["stderr"].rstrip())

        if result and not result["success"] and result["stderr"] and allow_heal:
            cl("WARN", "  [healing...]")
            fix = self.healer.heal(cmd, result["stderr"])
            if fix and fix != cmd:
                blocked2, _ = check(fix)
                if not blocked2:
                    cl("CMD", f"  ! retry: {fix}")
                    healed = self.jailbreak.run(fix)
                    if healed and healed["success"]:
                        result = healed
                        if healed.get("stdout"):
                            print(healed["stdout"].rstrip())
                        if healed.get("stderr"):
                            cl("ERR", healed["stderr"].rstrip())
                    elif healed and healed.get("stderr"):
                        cl("ERR", healed["stderr"].rstrip())

        success = result.get("success", False) if result else False
        audit_log({
            "t": time.time(), "action": "exec",
            "cmd": cmd, "mode": self.mode,
            "success": success, "duration": round(duration, 2),
        })

        return result

    def _exec_plugin(self, name, args=""):
        if name in self.plugins:
            cl("SYS", f"  [plugin] {name} {args}")
            try:
                output = self.plugins[name]["run"](args)
                if output:
                    print(output)
                return {"success": True, "output": output or ""}
            except Exception as e:
                msg = f"Plugin error: {e}"
                cl("ERR", f"  {msg}")
                return {"success": False, "output": msg}
        msg = f"Plugin '{name}' not found. Available: {list(self.plugins.keys())}"
        cl("ERR", f"  {msg}")
        return {"success": False, "output": msg}

    def _exec_shortcut(self, name, inp=None):
        cl("SYS", f"  [shortcut] {name}")
        self.jailbreak.run_shortcut(name, inp)

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
                parts = rest.split(None, 1)
                self._exec_shortcut(parts[0], parts[1] if len(parts) > 1 else None)
                result["success"] = True
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
            if last:
                cl("SYS", "Retrying last query...")
                ctx = self.memory.get_context()
                stripped = []
                for msg in ctx:
                    stripped.append(msg)
                    if msg is ctx[-1] or msg["role"] == "user":
                        continue
                self.memory.context = stripped
                self.memory.add("user", last)
                resp = self._stream()
                if resp:
                    print()
                    final = resp
                    if self.mode != "plan":
                        for rnd in range(5):
                            results = self._process_ai_response(final, heal=False)
                            if not results:
                                break
                            self.memory.add("tool", self._format_tool_results(results))
                            nxt = self._stream()
                            if nxt is None:
                                break
                            print()
                            final = nxt
                    prompt_chars = sum(len(m.get("content", "")) for m in self.memory.get_context())
                    self._show_stats(prompt_chars, len(final))
                    self.memory.add("assistant", final)
                    self.memory.cleanup()
            else:
                cl("ERR", "No previous query to retry.")

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

    def _stream(self, label="AI"):
        """Stream AI response with animated braille spinner."""
        stop = threading.Event()
        def spin():
            for char in itertools.cycle(PIXEL_SPINNER):
                if stop.is_set():
                    return
                sys.stdout.write(f"\r\033[K{ANSI['WARN']}{char}{ANSI['RST']} Thinking...")
                sys.stdout.flush()
                time.sleep(0.08)
        t = threading.Thread(target=spin, daemon=True)
        t.start()

        text = ""
        try:
            for token in self.bridge.stream(self.memory.get_context()):
                if not stop.is_set():
                    stop.set()
                    t.join()
                    sys.stdout.write(f"\r\033[K{ANSI[label]}{label}>{ANSI['RST']} ")
                sys.stdout.write(token)
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

            response = self._stream()
            if response is None:
                continue
            print()
            final = response

            if self.mode != "plan":
                for rnd in range(MAX_TOOL_ROUNDS):
                    results = self._process_ai_response(final, heal=False)
                    if not results:
                        break

                    self.memory.add("tool", self._format_tool_results(results))

                    next_resp = self._stream()
                    if next_resp is None:
                        break
                    print()
                    final = next_resp
            else:
                self._process_ai_response(response, heal=False)

            prompt_chars = sum(len(m.get("content", "")) for m in self.memory.get_context())
            self._show_stats(prompt_chars, len(final))
            self.memory.add("assistant", final)
            self.memory.cleanup()


if __name__ == "__main__":
    AION().run()
