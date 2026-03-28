"""
QMD Memory Plugin - Manual Setup/Reindex Script

Run this from the Agent Zero plugin execution UI to:
1. Ensure the memory directory structure exists
2. Register the memory directory as a QMD collection
3. Trigger a full reindex
"""

import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
QMD_ENGINE = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_ENGINE / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
MEMORY_DIR = Path("/a0/usr/memory")


def main():
    print("[QMD Memory] Starting manual setup...")

    # Check QMD
    if not QMD_CLI.exists():
        print(f"[QMD Memory] ERROR: QMD CLI not found at {QMD_CLI}")
        print("[QMD Memory] Please run hooks.install() or: cd qmd_engine && npm install @tobilu/qmd")
        return 1

    print(f"[QMD Memory] QMD CLI found: {QMD_CLI}")

    # Ensure memory directory
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (MEMORY_DIR / "sessions").mkdir(exist_ok=True)
    (MEMORY_DIR / "entities").mkdir(exist_ok=True)
    print(f"[QMD Memory] Memory directory ready: {MEMORY_DIR}")

    # Register collection
    print(f"[QMD Memory] Registering collection: {MEMORY_DIR}")
    result = subprocess.run(
        ["node", str(QMD_CLI), "collection", "add", str(MEMORY_DIR)],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Collection registration warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Collection registered successfully")

    # Run full reindex
    print("[QMD Memory] Starting full reindex (this may take a moment)...")
    result = subprocess.run(
        ["node", str(QMD_CLI), "update"],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Reindex warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Reindex complete!")

    # Check status
    try:
        result = subprocess.run(
            ["node", str(QMD_CLI), "status"],
            cwd=str(QMD_ENGINE),
            capture_output=True,
            text=True,
            timeout=15,
        )
        print(f"[QMD Memory] Status: {result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        print("[QMD Memory] Status check timed out (non-fatal, setup completed successfully)")
    print("[QMD Memory] Setup complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
