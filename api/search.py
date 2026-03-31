"""
QMD Memory Plugin - Search API Handler
POST /api/plugins/qmd_memory/search
"""

from pathlib import Path
from helpers.api import ApiHandler, Request, Response

PLUGIN_DIR = Path(__file__).parent.parent
QMD_DIR = PLUGIN_DIR / "qmd_engine"
QMD_CLI = QMD_DIR / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"


class Search(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        import json, subprocess

        query = input.get("query", "")
        limit = int(input.get("limit", 10))

        if not query:
            return Response("Query is required", status=400)

        if not QMD_CLI.exists():
            return {"ok": False, "error": "QMD not installed. Run the plugin execution script first."}

        try:
            result = subprocess.run(
                ["node", str(QMD_CLI), "query", query, "--json", "-n", str(limit)],
                cwd=str(QMD_DIR),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Search timed out"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "Search failed"}

        try:
            results = json.loads(result.stdout)
            return {"ok": True, "results": results}
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"Failed to parse results: {e}", "raw": result.stdout[:500]}
