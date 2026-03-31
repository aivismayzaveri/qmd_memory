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
DEFAULT_MEMORY_DIR = "/a0/usr/memory"


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

        memory_dir = Path(input.get("memory_dir", DEFAULT_MEMORY_DIR))
        session_count = 0
        if memory_dir.exists():
            session_count = sum(
                1 for f in memory_dir.glob("*.md")
                if f.stem.isdigit() and 9 <= len(f.stem) <= 10
            )

        return {
            "ok": True,
            "status": {
                "ready": result.returncode == 0,
                "qmd_installed": True,
                "memory_dir": str(memory_dir),
                "session_count": session_count,
                "output": result.stdout.strip(),
                "error": result.stderr.strip() if result.stderr.strip() else None,
            },
        }
