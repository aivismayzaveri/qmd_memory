"""
QMD Memory Plugin - Index API Handler
POST /api/plugins/qmd_memory/index
Triggers a background re-index of the memory directory.
"""

import subprocess
from pathlib import Path
from helpers.api import ApiHandler, Request, Response

PLUGIN_DIR = Path(__file__).parent.parent
QMD_DIR = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_DIR / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
DEFAULT_MEMORY_DIR = "/a0/usr/memory"


class Index(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        if not QMD_CLI.exists():
            return {"ok": False, "error": "QMD not installed. Run the plugin execution script first."}

        memory_dir = input.get("memory_dir", DEFAULT_MEMORY_DIR)

        # Register collection with name for qmd:// URI support
        if Path(memory_dir).exists():
            subprocess.run(
                ["node", str(QMD_CLI), "collection", "add", memory_dir, "--name", "sessions"],
                cwd=str(QMD_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Register context description (key QMD feature for LLM relevance)
            subprocess.run(
                ["node", str(QMD_CLI), "context", "add", "qmd://sessions",
                 "Agent interaction summaries with structured epochs"],
                cwd=str(QMD_DIR),
                capture_output=True,
                text=True,
                timeout=15,
            )

        # Step 1: rebuild BM25/text index (must complete before embedding)
        r = subprocess.run(
            ["node", str(QMD_CLI), "update"],
            cwd=str(QMD_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            return {"ok": False, "error": f"qmd update failed: {r.stderr.strip()[:200]}"}

        # Step 2: generate semantic embeddings for hybrid search
        subprocess.Popen(
            ["node", str(QMD_CLI), "embed"],
            cwd=str(QMD_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {"ok": True, "message": "Index rebuilt, embeddings generating in background", "memory_dir": memory_dir}
