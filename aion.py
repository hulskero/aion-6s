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
import logging
import threading

# Shrink thread stack from default 512KB → 128KB (saves ~75% per thread)
# threading.stack_size(128 * 1024)  # REMOVED — causes segfault on iOS

try:
    import readline
except ImportError:
    pass

# Lower recursion limit — safer on 2GB with 128KB stack
sys.setrecursionlimit(500)

# Use spawn instead of fork for subprocesses — avoids COW memory bloat
import multiprocessing
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    pass

# Tune GC for 2GB RAM: freeze startup objects, raise gen0 threshold
gc.collect(2)
gc.freeze()
gc.set_threshold(50_000, 10, 10)


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

LOGGER = logging.getLogger(__name__)

AUDIT_LOG = os.path.join(os.path.dirname(__file__), "aion-audit.log")


def c(color, text):
    sys.stdout.write(f"{ANSI[color]}{text}{ANSI['RST']}")
    sys.stdout.flush()


def cl(color, text):
    print(f"{ANSI[color]}{text}{ANSI['RST']}")


_SECRET_INDICATORS = ("nvapi-", "sk-", "ghp_", "@", "/Users/")
_SECRET_PATTERNS = [
    (re.compile(r'nvapi-[A-Za-z0-9\-_]{20,}'), 'nvapi-[REDACTED]'),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), 'sk-[REDACTED]'),
    (re.compile(r'ghp_[A-Za-z0-9]{20,}'), 'ghp_[REDACTED]'),
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[REDACTED_EMAIL]'),
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '[REDACTED_IP]'),
    (re.compile(r'/Users/[A-Za-z0-9_\-]+/'), '/Users/[REDACTED]/'),
]


def _obfuscate_secrets(text):
    if not any(ind in text for ind in _SECRET_INDICATORS):
        return text
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text

MAX_AUDIT_BYTES = 1_048_576  # 1 MB, overridden by config log_max_mb
_AUDIT_BUFFER = []
_AUDIT_FLUSH_INTERVAL = 5
_audit_lock = threading.Lock()
_audit_log_size = None


def _rotate_audit_log():
    global _audit_log_size
    try:
        if _audit_log_size is None:
            _audit_log_size = os.path.getsize(AUDIT_LOG)
        if _audit_log_size > MAX_AUDIT_BYTES:
            with open(AUDIT_LOG) as f:
                lines = f.readlines()
            with open(AUDIT_LOG, "w") as f:
                f.writelines(lines[-1000:])
            _audit_log_size = 0
    except Exception as e:
        LOGGER.debug("audit log rotate failed: %s", e)


def _flush_audit_buffer():
    global _audit_log_size
    with _audit_lock:
        if not _AUDIT_BUFFER:
            return
        try:
            with open(AUDIT_LOG, "a") as f:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    for entry in _AUDIT_BUFFER:
                        f.write(json.dumps(entry) + "\n")
                finally:
                    if fcntl:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            _AUDIT_BUFFER.clear()
            _audit_log_size = None
        except Exception as e:
            LOGGER.warning("audit buffer flush failed: %s", e)


def audit_log(entry):
    _rotate_audit_log()
    try:
        obfuscated = {}
        for k, v in entry.items():
            if isinstance(v, str):
                obfuscated[k] = _obfuscate_secrets(v)
            else:
                obfuscated[k] = v
        with _audit_lock:
            _AUDIT_BUFFER.append(obfuscated)
            buffer_len = len(_AUDIT_BUFFER)
        if buffer_len >= _AUDIT_FLUSH_INTERVAL:
            _flush_audit_buffer()
    except Exception as e:
        LOGGER.debug("audit_log entry failed: %s", e)


SESSION_DIR = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

PIXEL_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹⠸⠼⠳⠦⠧⠇⠏"

_AI_ACTION_RE = re.compile(r'@(cmd|plugin|shortcut|read|grep|glob)\s+(.+)', re.MULTILINE)

_WRITE_RE = re.compile(r'@write\s+(\S+)\n(.*?)(?=\n@|\Z)', re.DOTALL)
_EDIT_RE = re.compile(r'@edit\s+(\S+)\nOLD:\n(.*?)\nNEW:\n(.*?)(?=\n@|\Z)', re.DOTALL)


class AION:
    __slots__ = [
        "config", "bridge", "jailbreak", "memory",
        "healer", "plugins", "system_prompt", "mode",
        "config_path", "cmd_history", "last_user_msg",
        "workspace", "lock", "compact",
    ]

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.config = self._load_or_create_config()
        global MAX_AUDIT_BYTES
        mb = self.config.get("log_max_mb", 1)
        MAX_AUDIT_BYTES = int(mb) * 1024 * 1024
        self.mode = "chat"
        self.cmd_history = []
        self.last_user_msg = ""
        # Define workspace directory for sandboxing
        self.workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
        os.makedirs(self.workspace, exist_ok=True)
        self.lock = threading.Lock()
        self.compact = False
        self._init_components()

    def _validate_config(self, config):
        """Validate and sanitize config values"""
        if not isinstance(config, dict):
            return {
                "request_timeout": 90,
                "max_context_pairs": 5,
                "max_tokens": 512,
                "max_heal_attempts": 3,
                "temperature": 0.7,
                "rate_limit": 30,
                "retry_max": 5,
                "jailbreak_mode": "auto",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "model": "deepseek-ai/deepseek-v4-flash",
            }
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
        if not isinstance(tout, (int, float)) or tout < 30:
            config["request_timeout"] = 90
        elif tout > 180:
            config["request_timeout"] = 90

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
            elif "integrate.api.nvidia.com" not in url and not url.startswith("https://api.anthropic.com/"):
                cl("WARN", f"  [SECURITY] Unusual base_url: {url[:50]}")

        # Ensure all keys exist
        config.setdefault("api_key", "")
        config.setdefault("model", "deepseek-ai/deepseek-v4-flash")
        config.setdefault("base_url", "https://integrate.api.nvidia.com/v1")
        config.setdefault("jailbreak_mode", "auto")
        config.setdefault("temperature", 0.7)
        if "request_timeout" not in config:
            config["request_timeout"] = 90
        if "rate_limit" not in config:
            config["rate_limit"] = 30

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
            "rate_limit": 30,
            "retry_max": 5
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
                    if not key or len(key) < 40 or key == "nvapi-REPLACE-WITH-YOUR-KEY":
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
        for attempt in range(3):
            try:
                key = input("Enter NVIDIA API key (nvapi-xxx): ").strip()
                if key:
                    return key
            except (EOFError, KeyboardInterrupt):
                break
        cl("ERR", "No API key provided. Set NVIDIA_API_KEY env var or restart.")
        sys.exit(1)

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
            try:
                os.replace(tmp_path, self.config_path)
            except OSError:
                import shutil
                shutil.move(tmp_path, self.config_path)
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
        self.jailbreak = Jailbreak(
            self.config.get("jailbreak_mode", "auto"),
            workspace=self.workspace,
            timeout=self.config.get("request_timeout", 90),
        )
        self.memory = MemoryManager(self.config.get("max_context_pairs", 5))
        self.healer = SelfHeal(self.bridge, self.config.get("max_heal_attempts", 3))
        self.plugins = load_plugins(os.path.join(os.path.dirname(__file__), "plugins"))
        try:
            from plugins.ios_system import keep_awake
            keep_awake(True)
        except Exception:
            LOGGER.debug("keep_awake not available")
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

TOOLS:
{plugin_list}
  @cmd <shell command>     - run system command
  @shortcut run <name> [input]  - run iOS Shortcut
  @shortcut create <name>       - create iOS Shortcut
  @shortcut list                - list iOS Shortcuts
  @read <path> [start [end]]  - read file contents (optional line range)
  @write <path>            - write content to file (put content after @write line)
  @edit <path>             - replace text in file (use OLD:/NEW: blocks)
  @grep <pattern>          - search for pattern in source files
  @glob <pattern>          - find files matching glob pattern

HOW TO USE TOOLS:
When asked for something requiring a tool:

1. OUTPUT the tool (e.g. @plugin battery or @cmd pmset -g batt)
2. WAIT — system runs it and you see the result
3. GIVE FINAL ANSWER based on result

Example:
  User: "check battery"
  You: @plugin battery
  [system returns: "Battery: 85%, discharging"]
  You: "85%, discharging, ~3h remaining."

MODES (/plan, /build, /auto, /chat):
  plan  — list steps only, nothing executes
  build — propose steps, user confirms each
  auto  — execute immediately, guardrails block destruction
  chat  — normal chat, commands with warnings

SECURITY:
- NEVER @cmd with: rm -rf, dd, mkfs, reboot, poweroff, halt, chroot, sudo
- NEVER pipe curl/wget to sh/bash/python
- Commands over 500 chars blocked. Keep responses short (2GB RAM).

RULES:
- When a command fails, analyze and suggest a fix.
- In /plan: output numbered @cmd steps (they won't run).
- In /build: output @cmd + explanation per step."""

    def _exec_cmd(self, cmd, allow_heal=True):
        from core.guardrails import check, confirm, reset_confirm
        from core.input_validator import sanitize_input

        t0 = time.time()

        sane = sanitize_input(cmd)
        if sane is None:
            c("ERR", f"  ✗ $ {cmd}")
            print(f"{ANSI['GRY']}  │{ANSI['RST']} Input validation failed: invalid characters or too long")
            audit_log({"t": time.time(), "action": "blocked", "cmd": cmd, "reason": "input validation failed"})
            return None

        blocked, is_dest = check(cmd)
        if blocked:
            c("ERR", f"  ✗ $ {cmd}")
            print(f"{ANSI['GRY']}  │{ANSI['RST']} {blocked}")
            audit_log({"t": time.time(), "action": "blocked", "cmd": cmd, "reason": blocked})
            return None

        if self.mode == "plan":
            c("GRY", f"  [plan] $ {cmd}")
            print()
            return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

        if self.mode in ("chat", "build") and is_dest:
            cl("WARN", f"  [DANGEROUS] $ {cmd}")
            if not confirm(cmd):
                cl("WARN", "  Skipped.")
                audit_log({"t": time.time(), "action": "skipped", "cmd": cmd, "reason": "user declined"})
                return None

        with self.lock:
            self.cmd_history.append(cmd)
            if len(self.cmd_history) > 100:
                self.cmd_history = self.cmd_history[-50:]

        c("GRY", f"  ◎ $ {cmd}")
        result = self.jailbreak.run(cmd)

        duration = time.time() - t0

        ok = result and result.get("success")
        if self.compact:
            sys.stdout.write(f"  {'✓' if ok else '✗'} ({duration:.1f}s)\n")
        else:
            sys.stdout.write(f"  {ANSI['SYS'] if ok else ANSI['ERR']}{'✓' if ok else '✗'}{ANSI['RST']} ({duration:.1f}s)\n")

        self._print_output(result)

        if result and not result["success"] and result["stderr"] and allow_heal:
            if self.mode == "plan":
                return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}
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
                        self._print_output(healed)
                    else:
                        sys.stdout.write(f"  {ANSI['ERR']}✗{ANSI['RST']} ({dur2:.1f}s)\n")
                        self._print_output(healed)

        success = result.get("success", False) if result else False
        audit_log({
            "t": time.time(), "action": "exec",
            "cmd": cmd, "mode": self.mode,
            "success": success, "duration": round(duration, 2),
        })

        return result

    def _print_output(self, result):
        if self.compact:
            out = (result.get("stdout") or "").rstrip()[:200]
            if out:
                print(f"  {out}")
            return
        if result and result.get("stdout"):
            for line in result["stdout"].rstrip().split("\n"):
                print(f"{ANSI['GRY']}  │{ANSI['RST']} {line}")
        if result and result.get("stderr"):
            for line in result["stderr"].rstrip().split("\n"):
                print(f"{ANSI['GRY']}  │{ANSI['RST']} {ANSI['ERR']}{line}{ANSI['RST']}")

    def _read_file(self, path):
        parts = path.rsplit(None, 2)
        path = parts[0]
        offset = int(parts[1]) - 1 if len(parts) > 1 else 0
        limit = int(parts[2]) if len(parts) > 2 else None
        if offset < 0:
            offset = 0
        try:
            with open(path) as f:
                lines = f.readlines()
            if offset >= len(lines):
                return f"Start line {offset+1} beyond file length ({len(lines)})"
            selected = lines[offset:]
            if limit is not None:
                selected = selected[:limit]
            start_line = offset + 1
            max_digits = len(str(start_line + len(selected)))
            numbered = "".join(
                f"{i+start_line:>{max_digits}}|{line}" for i, line in enumerate(selected)
            )
            return numbered
        except FileNotFoundError:
            return f"File not found: {path}"
        except IsADirectoryError:
            return f"Is a directory: {path}"
        except OSError as e:
            return f"Error reading {path}: {e}"

    def _write_file(self, path, content):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"
        except OSError as e:
            return f"Error writing {path}: {e}"

    def _edit_file(self, path, old, new):
        try:
            with open(path) as f:
                content = f.read()
            if old not in content:
                return f"String not found in {path}"
            new_content = content.replace(old, new, 1)
            with open(path, "w") as f:
                f.write(new_content)
            return f"Edited 1 occurrence in {path}"
        except OSError as e:
            return f"Error editing {path}: {e}"

    def _grep_search(self, pattern):
        import fnmatch
        root = os.path.dirname(__file__)
        results = []
        pat = re.compile(pattern, re.IGNORECASE)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "sessions", "workspace"))]
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(dirpath, f)
                    try:
                        with open(path) as fh:
                            for i, line in enumerate(fh, 1):
                                if pat.search(line):
                                    rel = os.path.relpath(path, root)
                                    results.append(f"{rel}:{i}: {line.rstrip()}")
                    except (OSError, UnicodeDecodeError):
                        continue
        if not results:
            return "No matches found"
        return "\n".join(results[:50])

    def _glob_search(self, pattern):
        import glob as globmod
        try:
            root = os.path.dirname(os.path.abspath(__file__))
            full_pattern = pattern if pattern.startswith("/") else os.path.join(root, pattern)
            matches = sorted(globmod.glob(full_pattern, recursive=True))
            if not matches:
                return f"No files match: {pattern}"
            rel_matches = [os.path.relpath(m, root) for m in matches]
            return "\n".join(rel_matches[:50])
        except Exception as e:
            return f"Glob error: {e}"

    def _exec_plugin(self, name, args=""):
        if self.mode == "plan":
            c("GRY", f"  [plan] @plugin {name} {args}")
            print()
            return {"success": False, "output": ""}
        if name not in self.plugins:
            c("ERR", f"  ✗ @plugin {name} {args} — not found")
            msg = f"Plugin '{name}' not found. Available: {list(self.plugins.keys())}"
            return {"success": False, "output": msg}
        with self.lock:
            plugin = self.plugins.get(name)
            if plugin and plugin.pop("_lazy", None):
                from plugins import _load_plugin_module
                plugin["run"] = _load_plugin_module(plugin)
        t0 = time.time()
        c("GRY", f"  ◎ @plugin {name} {args}")
        try:
            output = plugin["run"](args)
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
        if self.mode == "plan":
            c("GRY", f"  [plan] @shortcut {text}")
            print()
            return {"success": False, "stdout": "", "stderr": "", "exit_code": -1}
        from core.input_validator import safe_shell_split
        parts = safe_shell_split(text)
        if not parts:
            cl("ERR", "  [shortcut] missing arguments")
            return {"success": False, "stdout": "", "stderr": "missing arguments", "exit_code": -1}
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

        for match in _WRITE_RE.finditer(text):
            path = match.group(1)
            content = match.group(2).strip()
            result = {"kind": "write", "input": path, "stdout": "", "success": False}
            result["stdout"] = self._write_file(path, content)
            result["success"] = not result["stdout"].startswith("Error")
            results.append(result)
            audit_log({"t": time.time(), "action": "write", "path": path})

        for match in _EDIT_RE.finditer(text):
            path = match.group(1)
            old = match.group(2)
            new = match.group(3)
            result = {"kind": "edit", "input": path, "stdout": "", "success": False}
            result["stdout"] = self._edit_file(path, old, new)
            result["success"] = not result["stdout"].startswith(("String not found", "Error"))
            results.append(result)
            audit_log({"t": time.time(), "action": "edit", "path": path})

        for match in _AI_ACTION_RE.finditer(text):
            kind = match.group(1)
            rest = match.group(2).strip().strip('"').strip("'")

            if kind in ("cmd",):
                cmd_res = self._exec_cmd(rest, allow_heal=heal)
                if cmd_res:
                    result = {
                        "kind": "cmd", "input": rest,
                        "stdout": (cmd_res.get("stdout") or "") + (cmd_res.get("stderr") or ""),
                        "success": cmd_res.get("success", False),
                        "exit_code": cmd_res.get("exit_code", 0),
                    }
                    results.append(result)
            elif kind == "plugin":
                parts = rest.split(None, 1)
                plugin_res = self._exec_plugin(parts[0], parts[1] if len(parts) > 1 else "")
                results.append({
                    "kind": "plugin", "input": rest,
                    "stdout": plugin_res["output"],
                    "success": plugin_res["success"],
                })
            elif kind == "shortcut":
                shortcut_res = self._exec_shortcut(rest)
                results.append({
                    "kind": "shortcut", "input": rest,
                    "stdout": (shortcut_res.get("stdout") or "") + (shortcut_res.get("stderr") or "") if shortcut_res else "",
                    "success": shortcut_res.get("success", True) if shortcut_res else True,
                })
            elif kind == "read":
                out = self._read_file(rest)
                success = not out.startswith(("File not found:", "Is a directory:", "Error reading", "Start line"))
                results.append({"kind": "read", "input": rest, "stdout": out, "success": success})
            elif kind == "grep":
                out = self._grep_search(rest)
                results.append({"kind": "grep", "input": rest, "stdout": out, "success": "No matches" not in out})
            elif kind == "glob":
                out = self._glob_search(rest)
                success = not (out.startswith("No files match") or out.startswith("Glob error"))
                results.append({"kind": "glob", "input": rest, "stdout": out, "success": success})

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
                    lines.append(out[:500])
            elif kind == "plugin":
                lines.append(f"[plugin] {inp}")
                out = (r.get("stdout") or "").rstrip()
                if out:
                    lines.append(out[:500])
            elif kind == "shortcut":
                lines.append(f"[shortcut] {inp}")
            elif kind == "read":
                lines.append(f"[read] {inp}")
                out = (r.get("stdout") or "").rstrip()
                if out:
                    lines.append(out[:2000])
            elif kind in ("write", "edit", "grep", "glob"):
                lines.append(f"[{kind}] {inp}")
                out = (r.get("stdout") or "").rstrip()
                if out:
                    lines.append(out)
        result = "\n".join(lines)
        return result[:2000] if len(result) > 2000 else result

    def _do_update(self, args=""):
        import subprocess as _sp
        import shutil as _su
        import tempfile as _tf
        import json as _json

        branch = "main"
        if args and not args.startswith("-"):
            branch = args.strip().split()[0]

        base_dir = os.path.dirname(os.path.abspath(__file__))
        repo_url = "https://github.com/hulskero/aion-6s.git"
        raw_base = f"https://raw.githubusercontent.com/hulskero/aion-6s/{branch}/"
        api_tree = f"https://api.github.com/repos/hulskero/aion-6s/git/trees/{branch}?recursive=1"

        updated = []
        skipped = []
        failed = []
        restored = []

        cl("SYS", f"Updating AION-6S from {branch}...")

        def _dl_file(rel_path):
            dest = os.path.join(base_dir, rel_path)
            bak = dest + ".bak"
            try:
                r = _sp.run(
                    ["curl", "-sL", raw_base + rel_path],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode != 0 or not r.stdout.strip():
                    return None
                content = r.stdout
                if rel_path.endswith(".py"):
                    try:
                        compile(content, rel_path, "exec")
                    except SyntaxError as e:
                        cl("ERR", f"  Syntax error in {rel_path}: {e}")
                        return None
                if os.path.exists(dest) and not os.path.exists(bak):
                    try:
                        _su.copy2(dest, bak)
                    except Exception:
                        LOGGER.debug("failed to backup %s", dest)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "w") as f:
                    f.write(content)
                return rel_path
            except Exception as e:
                cl("ERR", f"  Download failed {rel_path}: {e}")
                return None

        def _try_git():
            if not _su.which("git"):
                return None
            tmp = os.path.join(_tf.gettempdir(), "aion-6s_update")
            if os.path.exists(tmp):
                _su.rmtree(tmp, ignore_errors=True)
            cl("SYS", "  Using git...")
            r = _sp.run(
                ["git", "clone", "--depth", "1", "-b", branch, repo_url, tmp],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode != 0:
                cl("WARN", f"  git clone failed: {r.stderr.strip()[-200:]}")
                _su.rmtree(tmp, ignore_errors=True)
                return None
            py_files = []
            for root, dirs, files in os.walk(tmp):
                for f in files:
                    if not f.endswith((".py", ".json")):
                        continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, tmp)
                    if rel.startswith(".git") or rel.startswith("sessions") or rel.startswith("workspace") or rel.startswith("aion-6s/"):
                        continue
                    py_files.append((rel, full))
            for rel, full in py_files:
                dest = os.path.join(base_dir, rel)
                bak = dest + ".bak"
                try:
                    if rel.endswith(".py"):
                        with open(full) as _sf:
                            compile(_sf.read(), rel, "exec")
                    if os.path.exists(dest) and not os.path.exists(bak):
                        _su.copy2(dest, bak)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    _su.copy2(full, dest)
                    updated.append(rel)
                except SyntaxError as e:
                    cl("ERR", f"  Syntax error in {rel}: {e}")
                    failed.append(rel)
                    if os.path.exists(bak):
                        _su.copy2(bak, dest)
                        restored.append(rel)
                except Exception as e:
                    cl("ERR", f"  Copy failed {rel}: {e}")
                    failed.append(rel)
            _su.rmtree(tmp, ignore_errors=True)
            return True

        def _try_curl():
            cl("SYS", "  Using curl (no git)...")
            r = _sp.run(
                ["curl", "-sL", api_tree],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0 or not r.stdout.strip():
                cl("ERR", "  GitHub API unreachable")
                return False
            try:
                tree = _json.loads(r.stdout)
            except Exception:
                cl("ERR", "  Invalid GitHub API response")
                return False
            entries = tree.get("tree", [])
            py_entries = [e for e in entries if e["path"].endswith((".py", ".json")) and e["type"] == "blob"]
            if not py_entries:
                cl("ERR", "  No files found in GitHub tree")
                return False
            for entry in py_entries:
                rel = entry["path"]
                if rel.startswith(".git") or rel.startswith("sessions") or rel.startswith("workspace") or rel.startswith("aion-6s/"):
                    skipped.append(rel)
                    continue
                result = _dl_file(rel)
                if result:
                    updated.append(result)
                else:
                    failed.append(rel)
            return True

        git_ok = _try_git()
        if not git_ok:
            curl_ok = _try_curl()
            if not curl_ok:
                cl("ERR", "Update failed — no git and curl fallback failed")
                return

        if updated:
            cl("SYS", f"  Updated ({len(updated)}):")
            for f in updated:
                cl("SYS", f"    ✓ {f}")
        if failed:
            cl("ERR", f"  Failed ({len(failed)}):")
            for f in failed:
                cl("ERR", f"    ✗ {f}")
        if restored:
            cl("WARN", f"  Restored from backup ({len(restored)}):")
            for f in restored:
                cl("WARN", f"    ↺ {f}")
        if skipped:
            for f in skipped:
                cl("GRY", f"    - {f} (skipped)")

        if not failed:
            cl("SYS", "Update complete. Use /reload to reload plugins, or restart AION.")
        else:
            cl("WARN", "Update finished with errors — check above")

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
                    except (OSError, json.JSONDecodeError):
                        LOGGER.debug("failed to parse audit log line")
            else:
                cl("SYS", "No audit log yet.")

        elif cmd == "/plugins":
            cl("SYS", f"Plugins ({len(self.plugins)}):")
            for k, v in self.plugins.items():
                cl("SYS", f"  {k}: {v['description']}")

        elif line.startswith("/plugin install"):
            from plugins import install_plugin
            parts = line.split(None, 3)
            if len(parts) < 3:
                cl("ERR", "Usage: /plugin install <name> [url]")
                return
            p_name = parts[2]
            p_url = parts[3] if len(parts) > 3 else None
            if not p_url:
                cl("ERR", "Usage: /plugin install <name> <url>")
                return
            plugin, err = install_plugin(
                p_name, p_url,
                os.path.join(os.path.dirname(__file__), "plugins")
            )
            if err:
                cl("ERR", err)
            else:
                self.plugins[plugin["name"]] = plugin
                self.system_prompt = self._build_prompt()
                cl("SYS", f"Plugin '{plugin['name']}' installed and loaded.")

        elif line.startswith("/plugin remove"):
            from plugins import remove_plugin
            parts = line.split(None, 2)
            if len(parts) < 3:
                cl("ERR", "Usage: /plugin remove <name>")
                return
            ok, err = remove_plugin(
                parts[2],
                os.path.join(os.path.dirname(__file__), "plugins")
            )
            if err:
                cl("ERR", err)
            else:
                self.plugins = {
                    k: v for k, v in self.plugins.items()
                    if v["name"] != parts[2]
                }
                self.system_prompt = self._build_prompt()
                cl("SYS", f"Plugin '{parts[2]}' removed.")

        elif cmd.startswith("/event"):
            parts = cmd.split(None, 2)
            subcmd = parts[1].strip().lower() if len(parts) > 1 else ""
            if subcmd == "start":
                fifo = "/tmp/aion.event"
                self._ensure_fifo(fifo)
                cl("SYS", f"Event listener on {fifo} — Ctrl+C to stop")
                self._listen_events()
            elif subcmd == "once":
                fifo = "/tmp/aion.event"
                self._ensure_fifo(fifo)
                cl("SYS", "Waiting for one event...")
                event = self._read_event(fifo, timeout=30)
                if event:
                    cl("SYS", f"Event: {event}")
                    self._handle_event(event)
            else:
                cl("SYS",
                    "/event start  — listen for Activator events (Ctrl+C to exit)\n"
                    "/event once   — wait for one event, then stop\n\n"
                    "Activator setup: trigger → Run Command →\n"
                    '  echo "event:<name>" > /tmp/aion.state\n'
                    "  notify_post com.aion.event   (optional, reduces latency)")

        elif cmd == "/clear":
            self.memory.set_system(self.system_prompt)
            reset_confirm()
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

        elif cmd == "/compact":
            self.compact = not self.compact
            cl("SYS", f"Compact mode: {'ON' if self.compact else 'OFF'}")

        elif cmd == "/help":
            cl("SYS", f"""Commands:
  /plan              Plan mode — AI plans, nothing executes
  /build             Build mode — execute with step confirmation
  /auto              Auto mode — full autonomous, guardrails only
  /chat              Chat mode (default) — commands with warning
  /compact           Toggle compact output mode
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
  /plugin install <name> <url>   Install plugin from URL
  /plugin remove <name>         Remove a plugin
  /event start / once           Headless event listener for Activator
  /status            System status
  /log               Show last audit log entries
  /update            Download latest files from GitHub
  !! / !N            Repeat last / Nth command
  /help              This message

Direct tool commands:
  @read <path> [start [end]]  Read file (bypasses AI)
  @grep <pattern>            Search .py files for pattern
  @glob <pattern>            Find files matching glob
  !<command>                 Run shell command directly""")
        elif cmd == "/reload":
            import sys
            backup = {}
            for mod in list(sys.modules.keys()):
                if mod.startswith("core.") or mod == "core" or mod.startswith("plugins.") or mod == "plugins":
                    backup[mod] = sys.modules[mod]
                    del sys.modules[mod]
            try:
                self._init_components()
                self.system_prompt = self._build_prompt()
                cl("SYS", f"Core + plugins reloaded. {len(self.plugins)} active.")
            except Exception as e:
                sys.modules.update(backup)
                self._init_components()
                self.system_prompt = self._build_prompt()
                cl("ERR", f"/reload failed ({e}) — restored previous modules")

        elif cmd.startswith("/update"):
            self._do_update(cmd.split(None, 1)[1] if len(cmd.split(None, 1)) > 1 else "")

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
                "config": {k: v for k, v in self.config.items() if k != "api_key"},
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
                cl("SYS", "Available NVIDIA models:")
                cl("SYS", "  nvidia/nemotron-mini-4b-instruct     - Fastest (4B, low bandwidth)")
                cl("SYS", "  deepseek-ai/deepseek-v4-flash        - Balanced (default)")
                cl("SYS", "  deepseek-ai/deepseek-v4              - DeepSeek V4 full")
                cl("SYS", "  deepseek-ai/deepseek-v4-pro          - DeepSeek V4 Pro")
                cl("SYS", "  nvidia/llama-3.1-nemotron-70b       - Nemotron 70B")
                cl("SYS", "  nvidia/llama-3.3-nemotron-super-49b-v1  - Nemotron Super 49B")
                cl("SYS", "  nvidia/nvidia-nemotron-nano-9b-v2    - Nemotron Nano 9B v2")
                cl("SYS", f"Current: {self.config['model']}")
            else:
                new_model = parts[1].strip()
                valid_models = [
                    "nvidia/nemotron-mini-4b-instruct",
                    "deepseek-ai/deepseek-v4-flash",
                    "deepseek-ai/deepseek-v4",
                    "deepseek-ai/deepseek-v4-pro",
                    "nvidia/llama-3.1-nemotron-70b",
                    "nvidia/llama-3.3-nemotron-super-49b-v1",
                    "nvidia/nvidia-nemotron-nano-9b-v2",
                ]
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
        tokens = []
        try:
            for token in self.bridge.stream(self.memory.get_context()):
                if not stop.is_set():
                    stop.set()
                    t.join(timeout=2)
                    sys.stdout.write(f"\r\033[K{color}{label}>{ANSI['RST']} ")
                sys.stdout.write(f"{color}{token}{ANSI['RST']}")
                sys.stdout.flush()
                tokens.append(token)
        except (Exception, KeyboardInterrupt) as e:
            if not stop.is_set():
                stop.set()
                t.join(timeout=2)
            if isinstance(e, KeyboardInterrupt):
                cl("SYS", "\nInterrupted.")
            else:
                cl("ERR", f"\n[API Error] {e}")
            return None
        finally:
            if not stop.is_set():
                stop.set()
                t.join(timeout=2)
        return ''.join(tokens)

    def _show_stats(self, prompt_chars, completion_chars):
        usage = self.bridge.get_usage()
        if usage:
            prompt = usage.get("prompt_tokens", prompt_chars)
            completion = usage.get("completion_tokens", completion_chars)
        else:
            prompt = prompt_chars // 4
            completion = completion_chars // 4
        latency = getattr(self.bridge, "_last_latency", 0)
        if self.compact:
            cl("GRY", f"  ↑{prompt}t ↓{completion}t | {latency:.1f}s")
        else:
            cl("SYS", f"  ↑{prompt}t ↓{completion}t | {latency:.1f}s | {self.config['model']}")

    @staticmethod
    def _setup_notify():
        """Set up notify_post-based IPC. Returns (notify_post, notify_check, token).
        Falls back to (None, None, None) if ctypes/libc unavailable."""
        try:
            import ctypes
            libc = ctypes.CDLL("libc.dylib")
            notifier = libc.notify_post
            notifier.argtypes = [ctypes.c_char_p]
            notifier.restype = ctypes.c_uint32
            check_f = libc.notify_register_check
            check_f.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32)]
            check_f.restype = ctypes.c_uint32
            check = libc.notify_check
            check.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
            check.restype = ctypes.c_uint32
            token = ctypes.c_int32()
            status = check_f(b"com.aion.event", ctypes.byref(token))
            if status == 0:
                return notifier, check, token
        except Exception:
            LOGGER.debug("notify setup failed")
        return None, None, None

    def _ensure_fifo(self, path):
        """Create a named pipe (FIFO) for event-driven commands."""
        try:
            if not os.path.exists(path):
                os.mkfifo(path)
        except OSError:
            pass  # already exists or cannot create

    def _read_event(self, path, timeout=30):
        """Block-read a line from a named pipe with timeout."""
        import threading
        self._ensure_fifo(path)
        result = [None]
        def reader():
            try:
                with open(path) as f:
                    result[0] = f.readline().strip()
            except (OSError, ValueError):
                LOGGER.debug("event pipe read failed")
        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout)
        return result[0] if result[0] else None

    def _read_event_file(self, path="/tmp/aion.state"):
        try:
            if os.path.exists(path):
                with open(path) as f:
                    data = f.read().strip()
                if data:
                    return data
        except (OSError, ValueError):
            LOGGER.debug("event file read failed")
        return None

    def _handle_event(self, raw):
        raw = raw.removeprefix("event:").strip()
        cl("SYS", f"System event: {raw}")

        trigger_result = ""
        if "triggers" in self.plugins:
            try:
                trigger_result = self.plugins["triggers"]["run"](f"process {raw}")
            except Exception:
                LOGGER.warning("trigger run failed")

        if trigger_result == "ai" or trigger_result == "":
            handlers = {
                "wifi_joined": "WiFi connected — any action needed?",
                "wifi_left": "WiFi disconnected — switched to mobile data",
                "power_connected": "Device is now charging",
                "power_disconnected": "Device is on battery now",
                "lock": "Device locked — sleep mode",
                "unlock": "Device unlocked — ready",
            }
            prompt = handlers.get(raw, f"Event: {raw} — respond if relevant")
            self.memory.add("user", prompt)
            response = self._stream(gray=False)
            if response is None:
                return
            final = response
            for rnd in range(2):
                results = self._process_ai_response(final, heal=False)
                if not results:
                    break
                self.memory.add("tool", self._format_tool_results(results))
                nxt = self._stream(gray=False)
                if nxt is None:
                    break
                final = nxt
            self.memory.add("assistant", final)
            self.memory.cleanup()
        elif trigger_result.startswith("handled"):
            cl("GRY", f"  Trigger handled: {trigger_result}")
            audit_log({"t": time.time(), "action": "trigger", "event": raw, "result": trigger_result})

    def _listen_events(self, path="/tmp/aion.state"):
        import ctypes
        notify_post, notify_check, notify_token = self._setup_notify()
        cl("SYS", f"Event listener ready (notify_post + {path})")
        cl("SYS", "Setup: Activator → Run Command →")
        cl("SYS", f'  echo "event:wifi_joined" > {path} && notify_post com.aion.event')
        try:
            check_val = ctypes.c_int32()
            while True:
                if notify_check is not None and notify_token is not None:
                    check_val.value = 0
                    notify_check(notify_token, ctypes.byref(check_val))
                    if check_val.value:
                        data = self._read_event_file(path)
                        if data:
                            self._handle_event(data)
                time.sleep(0.5)
        except KeyboardInterrupt:
            cl("SYS", "Event listener stopped.")
        except Exception as e:
            cl("ERR", f"Event error: {e}")

    def run(self):
        MAX_TOOL_ROUNDS = 5
        cl("SYS", f"{ANSI['BOLD']}AION-6S{ANSI['RST']} ready  |  {len(self.plugins)} plugin(s)  |  {self.config['model']}")
        cl("SYS", f"Mode: {self.mode}  |  Type /help for commands.")

        while True:
            try:
                line = input(f"{ANSI['WARN']}{self.mode}>{ANSI['RST']} ")
            except (EOFError, KeyboardInterrupt):
                _flush_audit_buffer()
                try:
                    session_name = f"_autosave_{int(time.time())}"
                    save_path = os.path.join(SESSION_DIR, f"{session_name}.json")
                    data = {
                        "mode": self.mode,
                        "config": {k: v for k, v in self.config.items() if k != "api_key"},
                        "context": self.memory.get_context(),
                        "cmd_history": self.cmd_history[-20:],
                    }
                    with open(save_path, "w") as f:
                        json.dump(data, f)
                    cl("GRY", f"Session auto-saved: {session_name}")
                except Exception:
                    pass
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

            if line.startswith("!"):
                cmd = line[1:].strip()
                if not cmd:
                    cl("ERR", "Usage: !<command>")
                    continue
                r = self.jailbreak.run(cmd, timeout=15)
                self._print_output(r)
                continue

            if line.startswith("@read "):
                path = line[len("@read "):].strip()
                result = self._read_file(path)
                if result.startswith(("File not found:", "Is a directory:", "Error reading", "Start line")):
                    cl("ERR", result)
                else:
                    print(result)
                continue
            if line.startswith("@grep "):
                pattern = line[len("@grep "):].strip()
                result = self._grep_search(pattern)
                if "No matches" in result:
                    cl("GRY", result)
                else:
                    print(result)
                continue
            if line.startswith("@glob "):
                pattern = line[len("@glob "):].strip()
                result = self._glob_search(pattern)
                if result.startswith(("No files match", "Glob error")):
                    cl("ERR", result)
                else:
                    print(result)
                continue

            self.memory.add("user", line)

            response = self._stream(gray=False)
            if response is None:
                cl("ERR", "  API error — check /status or /log")
                continue
            final = response

            if self.mode != "plan":
                consecutive_failures = 0
                for rnd in range(MAX_TOOL_ROUNDS):
                    results = self._process_ai_response(final, heal=False)
                    if not results:
                        break

                    c("DIM", f"\n  \u2501 round {rnd+1}/{MAX_TOOL_ROUNDS} \u2501\n")

                    self.memory.add("tool", self._format_tool_results(results))

                    for r in results:
                        if not r.get("success", True):
                            consecutive_failures += 1
                        else:
                            consecutive_failures = 0
                    if consecutive_failures >= 3:
                        c("WARN", f"\n  \u23b9 circuit breaker: {consecutive_failures} consecutive tool failures\n")
                        break

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
