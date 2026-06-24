# AION-6S — AI Agent for iPhone 6s (iOS 15.8.5, Dopamine rootless)

## Overview
Minimal AI agent running on jailbroken iPhone 6s (2GB RAM). Uses NVIDIA NIM API (LLaMA 3.2 3B Instruct) via SSH/MCP tunnel from Mac. Zero pip deps on device — pure Python stdlib.

## Architecture
- `aion.py` — main AI agent (~1540 lines). 8 commands: /sysinfo, /free_mem, /uptime, /battery, /cpu, /net, /disk, /plugins, /info, /compact. Handles !shell and @read tool calls.
- `aion_daemon.py` — persistent daemon with Unix socket (`/tmp/aion-daemon.sock`) IPC. Pre-loads model, saves ~0.3s per call vs cold start.
- `aion_dclient.py` — client for daemon socket. Sends JSON commands, reads response.
- `aion_cmd.py` — headless executor. Auto-detects daemon socket → dispatches to daemon; fallback to direct mode.
- `core/bridge.py` — NVIDIA NIM API bridge (`https://api.nvcf.nim.com/v1/chat/completions`). Retry logic, JSON extraction.
- `core/guardrails.py` — output sanitizer (blocks IPs, shell commands, base64 encoded threats).
- `core/memory.py` — short-term session memory.
- `core/ios_hw.py` — device hardware introspection via `sysctl`, `hw`, `memorystatus`.
- `plugins/` — modular skill system: `battery.py`, `cpu.py`, `net.py`, `display.py`, `wifi.py`, `cellular.py`, `sensors.py`, `location.py`, `weather.py`, `voice.py`, `ios_system.py`, `activator.py`, `triggers.py`, `system_tools.py`, `tools.py`, `webfetch.py`, `shortcuts_bridge.py`.

## Quick Start
```bash
# Headless (direct mode)
export NVIDIA_API_KEY="nvapi-..."
python3 aion_cmd.py "how much RAM do I have?"

# Start daemon
python3 aion_daemon.py &

# Use daemon
python3 aion_dclient.py "/sysinfo"
python3 aion_dclient.py "/battery"
```

## Connection
- iPhone: `192.168.1.250:22` (ssh)
- MCP: `http://192.168.1.250:8090/mcp`
- Daemon: `/tmp/aion-daemon.sock`
- Daemon log: `/tmp/aion-daemon.log`

## Key Facts
- Model: `meta/llama-3.2-3b-instruct` (was `nvidia/nemotron-mini-4b-instruct` — safety filter blocked benign requests)
- API key from `NVIDIA_API_KEY` env var (NOT stored in config.json)
- ~147 MB avail RAM, 71.3G/119.2G disk, Battery: 70%, 23 cycles, 34.6°C
- iOS 15.8.5, Dopamine rootless, 15+ days uptime
- Python stdlib only — no pip/git deps on device
