#!/usr/bin/env python3
"""AION-6S: AI Operating Layer for Jailbroken iPhone 6s"""

import os
import sys
import json
import re
import gc


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


def c(color, text):
    sys.stdout.write(f"{ANSI[color]}{text}{ANSI['RST']}")
    sys.stdout.flush()


def cl(color, text):
    print(f"{ANSI[color]}{text}{ANSI['RST']}")


class AION:
    __slots__ = [
        "config", "bridge", "jailbreak", "memory",
        "healer", "plugins", "system_prompt", "mode",
        "config_path", "is_first_run",
    ]

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.config = self._load_or_create_config()
        self.mode = "chat"
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
            "max_tokens": 2048
        }

        # Try to load existing config
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    config = json.load(f)
                config = self._validate_config(config)
                # Check if api_key is missing or placeholder
                if not config.get("api_key") or config.get("api_key", "").startswith("nvapi-zWERU"):
                    config["api_key"] = self._prompt_api_key()
                    self._save_config(config)
                return config
            except Exception as e:
                cl("ERR", f"Config load error: {e}")
                return self._validate_config(self._prompt_config_interactive(default_config))

        cl("SYS", "First run detected. Please configure AION-6S.")
        return self._validate_config(self._prompt_config_interactive(default_config))

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
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    def _init_components(self):
        from core.bridge import Bridge
        from core.jailbreak import Jailbreak
        from core.memory import MemoryManager
        from core.self_heal import SelfHeal
        from core.guardrails import check, confirm, reset_confirm
        from plugins import load_plugins

        self.bridge = Bridge(self.config)
        self.jailbreak = Jailbreak(self.config.get("jailbreak_mode", "auto"))
        self.memory = MemoryManager(self.config.get("max_context_pairs", 5))
        self.healer = SelfHeal(self.bridge, self.config.get("max_heal_attempts", 3))
        self.plugins = load_plugins(os.path.join(os.path.dirname(__file__), "plugins"))
        self.system_prompt = self._build_prompt()
        self.memory.set_system(self.system_prompt)

    def _build_prompt(self):
        plugin_list = "\n".join(
            f"  @plugin {k} - {v['description']}"
            for k, v in self.plugins.items()
        ) or "  (none)"
        return f"""You are AION-6S on a jailbroken iPhone 6s (2GB RAM, a-Shell/NewTerm).

AVAILABLE:
{plugin_list}

COMMANDS:
  @cmd <shell command>     - Execute system command
  @plugin <name> [args]    - Run a plugin skill
  @shortcut <name> [input] - Run iOS Shortcut

MODES (user switches with /plan, /build, /auto, /chat):
  plan  — you list the steps, user reviews before any execute
  build — you propose steps, user confirms one by one
  auto  — you execute immediately, guardrails block destruction
  chat  — normal chat, commands execute with warnings

RULES:
- Be concise.
- When a command fails, analyze the error and suggest a fix.
- Memory is tight (2GB) — keep responses short.
- In /plan mode: output numbered steps using @cmd, they won't run.
- In /build mode: output @cmd and explain each step."""

    def _exec_cmd(self, cmd):
        from core.guardrails import check, confirm, reset_confirm

        blocked, is_dest = check(cmd)
        if blocked:
            cl("ERR", f"  {blocked}")
            return None

        if self.mode == "plan":
            cl("WARN", f"  [PLAN] Would run: $ {cmd}")
            return None

        if self.mode in ("chat", "build") and is_dest:
            cl("WARN", f"  [DANGEROUS] $ {cmd}")
            if not confirm(cmd):
                cl("WARN", "  Skipped.")
                return None

        cl("CMD", f"\n  $ {cmd}")
        result = self.jailbreak.run(cmd)

        if result and result["stdout"]:
            print(result["stdout"].rstrip())
        if result and result["stderr"]:
            cl("ERR", result["stderr"].rstrip())

        if result and not result["success"] and result["stderr"]:
            cl("WARN", "  [healing...]")
            fix = self.healer.heal(cmd, result["stderr"])
            if fix and fix != cmd:
                blocked2, _ = check(fix)
                if not blocked2:
                    cl("CMD", f"  ! retry: {fix}")
                    result2 = self.jailbreak.run(fix)
                    if result2:  # <-- FIX: Check if result2 is not None
                        if result2.get("stdout"):
                            print(result2["stdout"].rstrip())
                        if result2.get("stderr"):
                            cl("ERR", result2["stderr"].rstrip())

        return result

    def _exec_plugin(self, name, args=""):
        if name in self.plugins:
            cl("SYS", f"  [plugin] {name} {args}")
            output = self.plugins[name]["run"](args)
            print(output)
        else:
            cl("ERR", f"  Plugin '{name}' not found. Available: {list(self.plugins.keys())}")

    def _exec_shortcut(self, name, inp=None):
        cl("SYS", f"  [shortcut] {name}")
        self.jailbreak.run_shortcut(name, inp)

    def _process_ai_response(self, text):
        for match in re.finditer(r'@(cmd|plugin|shortcut)\s+(.+)', text, re.MULTILINE):
            kind = match.group(1)
            rest = match.group(2).strip().strip('"').strip("'")
            if kind == "cmd":
                self._exec_cmd(rest)
            elif kind == "plugin":
                parts = rest.split(None, 1)
                self._exec_plugin(parts[0], parts[1] if len(parts) > 1 else "")
            elif kind == "shortcut":
                parts = rest.split(None, 1)
                self._exec_shortcut(parts[0], parts[1] if len(parts) > 1 else None)

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

        elif cmd == "/plugins":
            cl("SYS", f"Plugins ({len(self.plugins)}):")
            for k, v in self.plugins.items():
                cl("SYS", f"  {k}: {v['description']}")

        elif cmd == "/clear":
            self.memory.set_system(self.system_prompt)
            cl("SYS", "Context cleared.")

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
  /info              System info
  /help              This message""")
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

    def run(self):
        cl("SYS", f"{ANSI['BOLD']}AION-6S{ANSI['RST']} ready  |  {len(self.plugins)} plugin(s)  |  {self.config['model']}")
        cl("SYS", f"Mode: {self.mode}  |  Type /help for commands.")

        while True:
            try:
                line = input(f"{ANSI['WARN']}{self.mode}>{ANSI['RST']} ")
            except (EOFError, KeyboardInterrupt):
                cl("SYS", "\nBye.")
                break

            if not line.strip():
                continue
            if line.startswith("/"):
                self._handle_special(line)
                continue

            self.memory.add("user", line)

            c("AI", "AI> ")
            full = ""
            try:
                for token in self.bridge.stream(self.memory.get_context()):
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    full += token
            except Exception as e:
                cl("ERR", f"\n[API Error] {e}")
                continue

            print()
            self.memory.add("assistant", full)

            if self.mode != "plan":
                self._process_ai_response(full)

            self.memory.cleanup()


if __name__ == "__main__":
    AION().run()
