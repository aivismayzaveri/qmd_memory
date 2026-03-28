"""
QMD Memory Plugin - Status API Handler
POST /api/plugins/qmd_memory/status
"""

import subprocess
from pathlib import Path
from helpers.api import ApiHandler, Request, Response

PLUGIN_DIR = Path(__file__).parent.parent
QMD_DIR = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_DIR / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
MEMORY_DIR = Path("/a0/usr/memory")


class Status(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        qmd_installed = QMD_CLI.exists()

        if not qmd_installed:
            return {
                "ok": True,
                "status": {
                    "ready": False,
                    "qmd_installed": False,
                    "message": "QMD not installed.",
                },
            }

        try:
            result = subprocess.run(
                ["node", str(QMD_CLI), "status"],
                cwd=str(QMD_DIR),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as e:
            return {"ok": True, "status": {"ready": False, "error": str(e)}}

        # Check memory dir state
        category_files = {
            "Facts.md": MEMORY_DIR / "Facts.md",
            "Goals.md": MEMORY_DIR / "Goals.md",
            "entities": MEMORY_DIR / "entities",
        }
        memory_stats = {k: v.exists() for k, v in category_files.items()}

        return {
            "ok": True,
            "status": {
                "ready": result.returncode == 0,
                "qmd_installed": True,
                "memory_dir": str(MEMORY_DIR),
                "memory_files": memory_stats,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() if result.stderr.strip() else None,
            },
        }
