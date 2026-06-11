"""
MEMEX CLI entry point.

Commands:
  memex init       — Initialize config and data directories
  memex doctor     — Pre-flight health check
  memex start      — Start the daemon
  memex chat       — Launch the TUI
  memex status     — Show daemon status
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import toml


def _default_config_path() -> Path:
    return Path.home() / ".memex" / "config.toml"


def _data_dir() -> Path:
    return Path(os.environ.get("MEMEX_DATA_DIR", str(Path.home() / ".memex")))


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize MEMEX configuration and data directories."""
    data_dir = _data_dir()
    config_path = _default_config_path()

    # Create directories
    for subdir in ["data", "logs"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Copy default config if not exists
    if not config_path.exists():
        default_config = Path(__file__).parent / "config" / "default_config.toml"
        if default_config.exists():
            shutil.copy2(str(default_config), str(config_path))
            print(f"✓ Created default config at {config_path}")
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("# MEMEX Configuration\n[daemon]\ndata_dir = ~/.memex\n")
            print(f"✓ Created minimal config at {config_path}")
    else:
        print(f"✓ Config already exists at {config_path}")

    # Set permissions
    os.chmod(str(data_dir), 0o700)
    print(f"✓ Data directory: {data_dir}")
    print(f"✓ Run 'memex doctor' to verify your setup")


def _check_disk_encryption() -> bool:
    """FIX: Actual disk encryption detection for macOS, Linux, and Windows.

    Returns True if encryption is detected or cannot be determined (optimistic).
    Returns False if encryption is explicitly reported as disabled.
    """
    import platform
    import subprocess
    system = platform.system()

    if system == "Darwin":
        # Check FileVault status via fdesetup
        try:
            result = subprocess.run(
                ["fdesetup", "status"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.strip().lower()
            if "filevault is on" in output:
                print("  ✓ FileVault disk encryption is ON")
                return True
            elif "filevault is off" in output:
                print("  ✗ FileVault is OFF — enable with: System Settings → Privacy & Security → FileVault")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        print("  ⚠ Cannot determine FileVault status (fdesetup not found)")
        return True  # Optimistic

    elif system == "Linux":
        # Check for LUKS via dmsetup or cryptsetup
        try:
            # Check if root is on a dm-crypt device
            result = subprocess.run(
                ["dmsetup", "ls", "--target", "crypt"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"  ✓ LUKS/dm-crypt encryption detected")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Check /etc/crypttab as fallback
        crypttab = Path("/etc/crypttab")
        if crypttab.exists():
            content = crypttab.read_text().strip()
            if content and not all(line.startswith("#") for line in content.splitlines()):
                print("  ✓ Encrypted volumes found in /etc/crypttab")
                return True

        # Check if home is on an encrypted filesystem
        try:
            result = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", "/"],
                capture_output=True, text=True, timeout=5,
            )
            source = result.stdout.strip()
            if "crypt" in source.lower():
                print(f"  ✓ Root filesystem is encrypted ({source})")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        print("  ⚠ No LUKS/dm-crypt encryption detected")
        print("    → Install and configure LUKS: https://gitlab.com/cryptsetup/cryptsetup")
        return True  # Optimistic — may be using other encryption

    elif system == "Windows":
        # Check BitLocker via manage-bde
        try:
            result = subprocess.run(
                ["manage-bde", "-status", "C:"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.lower()
            if "protection status:    protection on" in output:
                print("  ✓ BitLocker encryption is ON")
                return True
            elif "protection status:    protection off" in output:
                print("  ✗ BitLocker is OFF on C:")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        print("  ⚠ Cannot determine BitLocker status")
        return True

    return True  # Unknown OS — optimistic


def cmd_doctor(args: argparse.Namespace) -> None:
    """Pre-flight health check."""
    print("╔══════════════════════════════════════════╗")
    print("║         MEMEX Doctor — Health Check      ║")
    print("╚══════════════════════════════════════════╝")
    print()

    all_ok = True

    # Check data directory
    data_dir = _data_dir()
    if data_dir.exists():
        print(f"  ✓ Data directory exists: {data_dir}")
    else:
        print(f"  ✗ Data directory missing: {data_dir}")
        all_ok = False

    # Check config
    config_path = _default_config_path()
    if config_path.exists():
        try:
            toml.load(str(config_path))
            print(f"  ✓ Config valid: {config_path}")
        except Exception as e:
            print(f"  ✗ Config parse error: {e}")
            all_ok = False
    else:
        print(f"  ✗ Config not found. Run 'memex init' first.")
        all_ok = False

    # Check Ollama
    try:
        import httpx
        response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            models = [m.get("name", "") for m in response.json().get("models", [])]
            print(f"  ✓ Ollama running ({len(models)} models available)")

            # Check required models
            required_embed = "nomic-embed-text"
            required_chat = "llama3"

            embed_found = any(required_embed in m for m in models)
            chat_found = any(required_chat in m for m in models)

            if embed_found:
                print(f"  ✓ Embedding model available: {required_embed}")
            else:
                print(f"  ⚠ Embedding model not found: {required_embed}")
                print(f"    → Run: ollama pull {required_embed}")

            if chat_found:
                print(f"  ✓ Chat model available: {required_chat}")
            else:
                print(f"  ⚠ Chat model not found: {required_chat}")
                print(f"    → Run: ollama pull {required_chat}:8b")
        else:
            print(f"  ⚠ Ollama returned status {response.status_code}")
    except Exception:
        print("  ⚠ Ollama not reachable at localhost:11434")
        print("    → Install: https://ollama.com")
        print("    → Start: ollama serve")

    # Check Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 11):
        print(f"  ✓ Python {py_version}")
    else:
        print(f"  ✗ Python {py_version} (requires 3.11+)")
        all_ok = False

    # Check OS encryption — FIX: actual detection instead of print statement
    encryption_ok = _check_disk_encryption()
    if not encryption_ok:
        print("  ⚠ Disk encryption not detected. MEMEX stores sensitive data locally.")

    # Check directory permissions
    if data_dir.exists():
        mode = oct(data_dir.stat().st_mode)[-3:]
        if mode == "700":
            print(f"  ✓ Data directory permissions: {mode}")
        else:
            print(f"  ⚠ Data directory permissions: {mode} (recommended: 700)")

    print()
    if all_ok:
        print("  ✅ All checks passed. Ready to start.")
        print("  → Run: memex start")
    else:
        print("  ⚠️  Some checks need attention before starting.")


def cmd_start(args: argparse.Namespace) -> None:
    """Start the MEMEX daemon."""
    from .daemon import MEMEXDaemon

    daemon = MEMEXDaemon()
    daemon.run()


def cmd_chat(args: argparse.Namespace) -> None:
    """Launch the TUI chat interface."""
    from .tui.app import run_tui
    run_tui()


def cmd_status(args: argparse.Namespace) -> None:
    """Show daemon status via health endpoint."""
    import httpx
    try:
        response = httpx.get("http://127.0.0.1:7700/api/health", timeout=5.0)
        if response.status_code == 200:
            import json
            health = response.json()
            print(json.dumps(health, indent=2))
        else:
            print(f"Daemon returned status {response.status_code}")
    except Exception as e:
        print(f"Cannot reach MEMEX daemon: {e}")
        print("Is the daemon running? Start with: memex start")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="memex",
        description="MEMEX — Local-First Passive Second Brain",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    subparsers.add_parser("init", help="Initialize config and data directories")

    # doctor
    subparsers.add_parser("doctor", help="Pre-flight health check")

    # start
    start_parser = subparsers.add_parser("start", help="Start the daemon")
    start_parser.add_argument("--log-level", default="INFO", help="Log level")

    # chat
    subparsers.add_parser("chat", help="Launch the TUI chat interface")

    # status
    subparsers.add_parser("status", help="Show daemon status")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "start":
        cmd_start(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
