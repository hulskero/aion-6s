#!/usr/bin/env python3
"""AION-6S bootstrap — install deps + clone repo.

Usage on iPhone (NewTerm):
  python3 bootstrap.py  &&  python3 aion.py
"""
import os, sys, subprocess, urllib.request, json

BASE = "https://api.github.com/repos/hulskero/aion-6s"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

def info(msg):
    print(f"{GREEN}[✓]{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}[!]{RESET} {msg}")

def fail(msg):
    print(f"{RED}[✗]{RESET} {msg}")
    return False

def run(cmd, **kwargs):
    kwargs.setdefault("timeout", 60)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        return r
    except FileNotFoundError:
        return None

def check_pkg(name, apt_name=None):
    """Check if a package is installed via apt."""
    r = run(["dpkg", "-s", apt_name or name], timeout=10)
    return r and r.returncode == 0

def apt_install(pkgs):
    """Install packages via apt with error handling."""
    for pkg in pkgs:
        if check_pkg(pkg):
            info(f"{pkg} already installed")
        else:
            warn(f"Installing {pkg} (needs root)...")
            r = run(["apt", "install", "-y", pkg], timeout=120)
            if r and r.returncode == 0:
                info(f"{pkg} installed")
            else:
                fail(f"Failed to install {pkg}. Run: sudo apt install -y {pkg}")
                return False
    return True

def download_repo(target):
    """Download repo tarball from GitHub and extract."""
    url = f"{BASE}/tarball/main"
    tarpath = "/tmp/aion-bootstrap.tar.gz"
    warn(f"Downloading AION-6S from GitHub...")
    try:
        urllib.request.urlretrieve(url, tarpath)
    except Exception as e:
        return fail(f"Download failed: {e}")
    info("Downloaded")

    if os.path.exists(target):
        run(["rm", "-rf", target])

    r = run(["tar", "-xzf", tarpath], cwd="/tmp")
    if not r or r.returncode != 0:
        return fail("Extract failed")

    extracted = [d for d in os.listdir("/tmp") if d.startswith("hulskero-aion-6s-")]
    if not extracted:
        return fail("No extracted directory found")
    os.rename(f"/tmp/{extracted[0]}", target)
    info(f"Extracted to {target}")
    return True

def setup_config():
    """Create config.json from example if not exists."""
    config_path = os.path.join(os.getcwd(), "config.json")
    example_path = os.path.join(os.getcwd(), "config.example.json")
    if os.path.exists(config_path):
        info("config.json exists")
        return True
    if os.path.exists(example_path):
        import shutil
        shutil.copy2(example_path, config_path)
        warn("config.json created from config.example.json")
        warn(f"  Edit it: nano {config_path}")
        warn(f"  Add your NVIDIA_API_KEY")
    else:
        fail("No config.example.json found")
        return False
    return True

def verify_plugins():
    """Quick check that key dependencies work."""
    checks = [
        ("python3", ["python3", "-c", "import ctypes; print('ctypes ok')"]),
    ]
    for name, cmd in checks:
        r = run(cmd, timeout=10)
        if r and r.returncode == 0:
            info(f"{name} works")
        else:
            warn(f"{name}: {r.stderr[:100] if r and r.stderr else 'not found'}")

def main():
    print(f"{BOLD}AION-6S Bootstrap{RESET}")
    print()

    target = os.path.join(os.getcwd(), "aion-6s")

    # Detect jailbreak mode
    is_jailbroken = os.path.exists("/var/jb") or os.path.exists("/var/mobile")

    if is_jailbroken:
        info("Jailbroken iPhone detected")
    else:
        warn("Not a jailbroken device — some plugins may not work")
        print("Continuing with code download only...\n")

    # Install system dependencies (jailbroken only)
    system_pkgs = []
    if is_jailbroken:
        # Check for apt
        r = run(["which", "apt"])
        if r and r.returncode == 0 and os.geteuid() == 0:
            run(["apt", "update"], timeout=60)
            system_pkgs = ["iokittools"]
            apt_install(system_pkgs)
        else:
            warn("Not running as root — skipping apt installs")
            warn("  Run: sudo python3 bootstrap.py")
            warn("  Or install manually: sudo apt install iokittools")

    # Download code
    if download_repo(target):
        os.chdir(target)
    else:
        return 1

    # Config
    setup_config()

    # Install Python deps
    r = run(["python3", "-m", "pip", "install", "-r", "requirements.txt"], timeout=60)
    if r and r.returncode == 0:
        info("Python dependencies installed")
    else:
        warn("pip install failed (non-critical, core uses stdlib)")

    # Verify
    verify_plugins()

    # Done
    print(f"\n{BOLD}Done!{RESET}")
    print(f"  cd ~/Documents/aion-6s")
    print(f"  python3 aion.py")
    print()

if __name__ == "__main__":
    sys.exit(main())
