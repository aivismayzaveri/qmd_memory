"""
QMD Memory Plugin - Session File Manager

Handles directory setup and atomic writes for session memory files.
"""

import os
import tempfile
from pathlib import Path


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a temp file then rename atomically to prevent corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def ensure_memory_structure(memory_dir: str) -> None:
    """Create the memory directory if it doesn't exist."""
    Path(memory_dir).mkdir(parents=True, exist_ok=True)
