"""
QMD Memory Plugin - Installation Hooks
"""

import subprocess
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
QMD_ENGINE_DIR = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_ENGINE_DIR / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"


def install():
    """Called after plugin is installed. Sets up the qmd_engine with @tobilu/qmd."""
    print("[QMD Memory] Starting installation...")

    if not _ensure_qmd_cli():
        return 1

    # Create default memory directory structure
    memory_dir = Path("/a0/usr/memory")
    _ensure_memory_structure(memory_dir)
    print(f"[QMD Memory] Memory directory ready at {memory_dir}")
    print("[QMD Memory] Installation complete!")
    return 0


def uninstall():
    """Called before plugin is uninstalled."""
    print("[QMD Memory] Uninstalling...")
    print("[QMD Memory] Uninstall complete. Memory data at /a0/usr/memory is preserved.")
    return 0


def pre_update():
    """Called before plugin is updated."""
    print("[QMD Memory] Pre-update hook called")
    return 0


def _ensure_qmd_cli() -> bool:
    """Ensure @tobilu/qmd CLI is installed in qmd_engine/. Returns True on success."""
    if QMD_CLI.exists():
        print(f"[QMD Memory] QMD CLI already present at {QMD_CLI}")
        return True

    # Check Node.js is available
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
    print("[QMD Memory] QMD installed successfully")
    return True


def _ensure_memory_structure(memory_dir: Path):
    """Create the memory directory structure with initial empty files."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "sessions").mkdir(exist_ok=True)
    (memory_dir / "entities").mkdir(exist_ok=True)

    # Entity sub-files
    entity_subtypes = ["people", "projects", "technologies", "organizations", "places", "other"]
    for subtype in entity_subtypes:
        f = memory_dir / "entities" / f"{subtype}.md"
        if not f.exists():
            f.write_text(f"""---
schema_version: 1
type: entities
subtype: {subtype}
last_updated: "{now}"
---

# {subtype.capitalize()}
""")

    # Entity index
    idx = memory_dir / "entities" / "_index.md"
    if not idx.exists():
        idx.write_text(f"""---
schema_version: 1
type: entities_index
last_updated: "{now}"
---

# Entity Index

| Name | Type | File | Last Updated |
|------|------|------|--------------|
""")

    # Top-level category files
    categories = {
        "Episodes.md": ("episodes", "# Episodes\n"),
        "Facts.md": ("facts", "# Facts\n\n## User Preferences\n\n## Project Information\n\n## References & Links\n"),
        "Knowledge.md": ("knowledge", "# Knowledge\n"),
        "Procedure.md": ("procedure", "# Procedures\n"),
        "Goals.md": ("goals", "# Goals\n\n## Active\n\n## Completed\n"),
        "Guardrails.md": ("guardrails", "# Guardrails\n\n## Security\n\n## Interaction Preferences\n\n## Code Style\n"),
    }
    for filename, (cat_type, body) in categories.items():
        f = memory_dir / filename
        if not f.exists():
            f.write_text(f"""---
schema_version: 1
type: {cat_type}
last_updated: "{now}"
---

{body}""")
