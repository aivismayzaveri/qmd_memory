"""
QMD Memory Plugin - Manual Setup/Reindex Script

Run this from the Agent Zero plugin execution UI to:
1. Ensure the memory directory structure exists
2. Register the memory directory as a QMD collection
3. Trigger a full reindex
4. If entity_glinker_enabled: true, download and warm the GLinker model
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

PLUGIN_DIR = Path(__file__).parent
QMD_ENGINE = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_ENGINE / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"

# Config resolution order (first found wins):
#   1. usr/.a0/plugins/qmd_memory/config.json  (saved from the UI)
#   2. plugin default_config.yaml
_CONFIG_OVERRIDE = Path("/a0/usr/.a0/plugins/qmd_memory/config.json")
_CONFIG_DEFAULT = PLUGIN_DIR / "default_config.yaml"


def _load_config() -> dict:
    """Load plugin config — UI override first, then YAML defaults."""
    defaults = {}
    if _CONFIG_DEFAULT.exists():
        with open(_CONFIG_DEFAULT, encoding="utf-8") as f:
            defaults = yaml.safe_load(f) or {}

    overrides = {}
    if _CONFIG_OVERRIDE.exists():
        with open(_CONFIG_OVERRIDE, encoding="utf-8") as f:
            overrides = json.load(f) or {}

    return {**defaults, **overrides}


def _setup_glinker(config: dict) -> None:
    """
    Download and warm the GLinker model if entity_glinker_enabled is true.

    This triggers the Hugging Face download on first run so it is cached
    locally before the plugin uses it during extraction.
    """
    model = config.get("entity_glinker_model", "knowledgator/gliner-linker-base-v1.0")
    device = config.get("entity_glinker_device", "cpu")
    threshold = float(config.get("entity_glinker_threshold", 0.75))

    print(f"[QMD Memory] GLinker enabled — checking model '{model}'...")

    # Ensure glinker is installed
    try:
        from glinker import ProcessorFactory  # noqa: F401
    except ImportError:
        print("[QMD Memory] glinker package not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "glinker"],
            capture_output=False,
            timeout=300,
        )
        if result.returncode != 0:
            print("[QMD Memory] WARNING: glinker install failed. Tier-2 entity dedup will be unavailable.")
            return
        from glinker import ProcessorFactory  # noqa: F401

    # Warm the model: build a minimal executor so Hugging Face downloads and
    # caches the model weights. We pass a dummy entity list — the goal here is
    # just to trigger the download, not to do any real linking.
    print(f"[QMD Memory] Warming GLinker model (this may take a few minutes on first run)...")
    try:
        from glinker import ProcessorFactory

        dummy_entities = [{"entity_id": "test", "label": "test", "description": "warmup entity"}]
        executor = ProcessorFactory.create_simple(
            model_name=model,
            device=device,
            threshold=0.40,
            template="{label}: {description}",
            entities=dummy_entities,
            precompute_embeddings=True,
            verbose=False,
        )
        # Run one dummy inference to confirm the model is fully loaded
        executor.execute({"texts": ["warmup test (misc)"]})
        del executor
        print(f"[QMD Memory] GLinker model '{model}' is ready and cached.")
    except Exception as e:
        print(f"[QMD Memory] WARNING: GLinker model warmup failed: {e}")
        print("[QMD Memory] Tier-2 entity dedup may not work. Check model name and device.")


def _install_soft_deps() -> None:
    """Install optional Python dependencies for full plugin functionality."""
    soft_deps = {
        "rapidfuzz": "rapidfuzz",           # Tier-1 fuzzy entity dedup
        "pdfminer": "pdfminer.six",         # PDF import
        "pypdf": "pypdf",                   # PDF import fallback
        "markdownify": "markdownify",       # HTML import
    }
    for import_name, pip_name in soft_deps.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"[QMD Memory] Installing optional dependency: {pip_name}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pip_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                print(f"[QMD Memory] WARNING: {pip_name} install failed (non-critical): {result.stderr[:100]}")
            else:
                print(f"[QMD Memory] {pip_name} installed successfully")


def main():
    print("[QMD Memory] Starting manual setup...")

    # Load config (UI overrides + YAML defaults)
    config = _load_config()
    memory_dir = Path(config.get("memory_dir", "/a0/usr/memory"))

    # Check QMD
    if not QMD_CLI.exists():
        print(f"[QMD Memory] ERROR: QMD CLI not found at {QMD_CLI}")
        print("[QMD Memory] Please run hooks.install() or: cd qmd_engine && npm install @tobilu/qmd")
        return 1

    print(f"[QMD Memory] QMD CLI found: {QMD_CLI}")

    # Ensure memory directory
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "sessions").mkdir(exist_ok=True)
    (memory_dir / "entities").mkdir(exist_ok=True)
    print(f"[QMD Memory] Memory directory ready: {memory_dir}")

    # Register collection
    print(f"[QMD Memory] Registering collection: {memory_dir}")
    result = subprocess.run(
        ["node", str(QMD_CLI), "collection", "add", str(memory_dir)],
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

    # Install optional Python dependencies
    print("[QMD Memory] Checking optional dependencies...")
    _install_soft_deps()

    # GLinker model download (only if enabled in config)
    if config.get("entity_glinker_enabled", False):
        _setup_glinker(config)
    else:
        print("[QMD Memory] GLinker (Tier-2 entity dedup) is disabled — skipping model download.")
        print("[QMD Memory] To enable: turn on 'GLinker semantic linking' in plugin settings, then run Execute again.")

    print("[QMD Memory] Setup complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
