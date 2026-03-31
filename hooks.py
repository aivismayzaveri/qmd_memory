"""
QMD Memory Plugin - Installation Hooks
"""

import os
import subprocess
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
QMD_ENGINE_DIR = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_ENGINE_DIR / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"


def install():
    """Called after plugin is installed. Ensures QMD CLI is present and memory dir exists."""
    print("[QMD Memory] Starting installation...")

    if not _ensure_qmd_cli():
        return 1

    # Make QMD CLI globally available
    _install_global_qmd()

    memory_dir = Path("/a0/usr/memory")
    memory_dir.mkdir(parents=True, exist_ok=True)
    print(f"[QMD Memory] Memory directory ready at {memory_dir}")
    print("[QMD Memory] Installation complete!")
    return 0


def uninstall():
    """Called before plugin is uninstalled."""
    print("[QMD Memory] Uninstalling...")
    print("[QMD Memory] Session data at /a0/usr/memory is preserved.")
    return 0


def pre_update():
    """Called before plugin is updated."""
    print("[QMD Memory] Pre-update hook called")
    return 0


def _install_global_qmd() -> None:
    """Create /usr/local/bin/qmd wrapper so `qmd` is available system-wide."""
    wrapper_path = Path("/usr/local/bin/qmd")
    wrapper_content = f"""#!/bin/sh
exec node "{QMD_CLI}" "$@"
"""
    try:
        wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        wrapper_path.write_text(wrapper_content)
        os.chmod(str(wrapper_path), 0o755)
        print(f"[QMD Memory] Global QMD CLI installed: {wrapper_path}")
    except Exception as e:
        print(f"[QMD Memory] Global CLI install skipped: {e}")


def _ensure_qmd_cli() -> bool:
    """Ensure @tobilu/qmd CLI is installed in qmd_engine/. Returns True on success."""
    if QMD_CLI.exists():
        print(f"[QMD Memory] QMD CLI already present.")
        return True

    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("[QMD Memory] ERROR: Node.js not found")
            return False
    except FileNotFoundError:
        print("[QMD Memory] ERROR: Node.js not installed")
        return False

    print("[QMD Memory] Installing @tobilu/qmd...")
    QMD_ENGINE_DIR.mkdir(exist_ok=True)
    subprocess.run(["npm", "init", "-y"], cwd=str(QMD_ENGINE_DIR), capture_output=True, timeout=30)
    result = subprocess.run(
        ["npm", "install", "@tobilu/qmd"],
        cwd=str(QMD_ENGINE_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] ERROR: npm install failed: {result.stderr}")
        return False
    print("[QMD Memory] QMD installed successfully.")
    return True
