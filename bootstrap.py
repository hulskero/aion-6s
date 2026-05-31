#!/usr/bin/env python3
"""AION-6S bootstrap — stáhne kompletní repozitář z GitHubu.
Použití na iPhonu (a-Shell):  python3 bootstrap.py  &&  cd aion-6s  &&  python3 aion.py
"""
import os, sys, urllib.request, json

BASE = "https://raw.githubusercontent.com/hulskero/aion-6s/main"
FILES = {
    "aion.py": "aion.py",
    "config.example.json": "config.example.json",
    "README.md": "README.md",
    ".gitignore": ".gitignore",
    "core/__init__.py": "core/__init__.py",
    "core/bridge.py": "core/bridge.py",
    "core/jailbreak.py": "core/jailbreak.py",
    "core/memory.py": "core/memory.py",
    "core/guardrails.py": "core/guardrails.py",
    "core/self_heal.py": "core/self_heal.py",
    "core/input_validator.py": "core/input_validator.py",
    "plugins/__init__.py": "plugins/__init__.py",
    "plugins/system_tools.py": "plugins/system_tools.py",
    "plugins/nfc_manager.py": "plugins/nfc_manager.py",
    "plugins/battery.py": "plugins/battery.py",
    "plugins/location.py": "plugins/location.py",
    "plugins/webfetch.py": "plugins/webfetch.py",
    "plugins/weather.py": "plugins/weather.py",
}

def main():
    root = os.path.join(os.getcwd(), "aion-6s")
    total = len(FILES)
    ok = 0
    for relpath, name in FILES.items():
        path = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = f"{BASE}/{relpath}"
        sys.stdout.write(f"  {name} ... ")
        sys.stdout.flush()
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            sys.stdout.write("OK\n")
            ok += 1
        except Exception as e:
            sys.stdout.write(f"FAIL: {e}\n")
    print(f"\nStaženo {ok}/{total} souborů do {root}")
    print(f"\nSpusť:")
    print(f"  cd {root}")
    print(f"  python3 aion.py")

if __name__ == "__main__":
    main()