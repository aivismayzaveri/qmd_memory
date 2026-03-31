"""
QMD Memory Plugin - Manual Setup/Reindex Script

Run this from the Agent Zero plugin execution UI to:
1. Ensure the memory directory exists
2. Make the QMD CLI globally available (symlink to /usr/local/bin/qmd)
3. Register session collection with QMD (qmd collection add --name sessions)
4. Register collection context for LLM relevance (qmd context add)
5. Build BM25 text index (qmd update)
6. Generate semantic embeddings for hybrid search (qmd embed)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
QMD_ENGINE = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_ENGINE / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"

_CONFIG_OVERRIDE = Path("/a0/usr/.a0/plugins/qmd_memory/config.json")
_CONFIG_DEFAULT = PLUGIN_DIR / "default_config.yaml"


def _load_config() -> dict:
    """Load plugin config — UI override first, then YAML defaults."""
    defaults = {}
    if _CONFIG_DEFAULT.exists():
        # Parse only the lines we need without requiring pyyaml
        raw = _CONFIG_DEFAULT.read_text(encoding="utf-8")
        for line in raw.splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                defaults[k.strip()] = v.strip().strip('"')

    overrides = {}
    if _CONFIG_OVERRIDE.exists():
        with open(_CONFIG_OVERRIDE, encoding="utf-8") as f:
            overrides = json.load(f) or {}

    return {**defaults, **overrides}


def _install_global_qmd(cli_path: Path) -> None:
    """Create /usr/local/bin/qmd wrapper so `qmd` is available system-wide."""
    wrapper_path = Path("/usr/local/bin/qmd")
    wrapper_content = f"""#!/bin/sh
exec node "{cli_path}" "$@"
"""
    try:
        wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        wrapper_path.write_text(wrapper_content)
        os.chmod(str(wrapper_path), 0o755)
        print(f"[QMD Memory] Global QMD CLI installed: {wrapper_path}")
    except PermissionError:
        print(f"[QMD Memory] Could not install global CLI at {wrapper_path} (permission denied).")
        print("[QMD Memory] Run manually: sudo ln -sf ... or use 'node <qmd.js>' directly.")
    except Exception as e:
        print(f"[QMD Memory] Global CLI install warning: {e}")


def main():
    print("[QMD Memory] Starting setup...")

    config = _load_config()
    memory_dir = Path(config.get("memory_dir", "/a0/usr/memory"))

    # Check QMD CLI
    if not QMD_CLI.exists():
        print(f"[QMD Memory] ERROR: QMD CLI not found at {QMD_CLI}")
        print("[QMD Memory] Run: cd qmd_engine && npm install @tobilu/qmd")
        return 1

    print(f"[QMD Memory] QMD CLI found: {QMD_CLI}")

    # Make QMD CLI globally available
    _install_global_qmd(QMD_CLI)

    # Ensure memory directory exists
    memory_dir.mkdir(parents=True, exist_ok=True)
    print(f"[QMD Memory] Memory directory ready: {memory_dir}")

    # Register collection: qmd collection add <memory_dir> --name sessions
    print(f"[QMD Memory] Registering collection: {memory_dir} --name sessions")
    result = subprocess.run(
        ["node", str(QMD_CLI), "collection", "add", str(memory_dir), "--name", "sessions"],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Collection registration warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Collection registered as 'sessions'.")

    # Register context: qmd context add qmd://sessions "<description>"
    # This is QMD's key feature — context descriptions are returned alongside
    # search results so LLMs can make better relevance decisions.
    print("[QMD Memory] Registering collection context...")
    result = subprocess.run(
        ["node", str(QMD_CLI), "context", "add", "qmd://sessions",
         "Agent interaction summaries with structured epochs"],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Context registration warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Context registered.")

    # Build BM25 text index
    print("[QMD Memory] Running text reindex (qmd update)...")
    result = subprocess.run(
        ["node", str(QMD_CLI), "update"],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Reindex warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Text reindex complete.")

    # Generate semantic embeddings (needed for hybrid qmd query)
    print("[QMD Memory] Generating semantic embeddings (qmd embed)...")
    result = subprocess.run(
        ["node", str(QMD_CLI), "embed"],
        cwd=str(QMD_ENGINE),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"[QMD Memory] Embed warning: {result.stderr.strip()}")
    else:
        print("[QMD Memory] Embeddings generated.")

    # Status check
    try:
        result = subprocess.run(
            ["node", str(QMD_CLI), "status"],
            cwd=str(QMD_ENGINE),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout.strip():
            print(f"[QMD Memory] Status: {result.stdout.strip()}")
    except Exception:
        print("[QMD Memory] Status check skipped (non-fatal).")

    print("[QMD Memory] Setup complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
