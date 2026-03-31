from helpers.tool import Tool, Response
from helpers import plugins
from pathlib import Path
import re


class MemoryBrowse(Tool):

    async def execute(self, count=20, **kwargs) -> Response:
        """List recent sessions in reverse-chronological order (newest first)."""
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        memory_dir = Path(config.get("memory_dir", "/a0/usr/memory"))

        try:
            count = int(count)
        except (ValueError, TypeError):
            count = 20

        try:
            session_files = sorted(
                [f for f in memory_dir.glob("*.md") if f.stem.isdigit() and 9 <= len(f.stem) <= 10],
                reverse=True,
            )[:count]

            if not session_files:
                return Response(message="No sessions recorded yet.", break_loop=False)

            lines = [f"# Recent Sessions ({len(session_files)} of {self._total_count(memory_dir)})\n"]
            for sf in session_files:
                content = sf.read_text(encoding="utf-8")
                summary_match = re.search(r'^summary:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
                summary = summary_match.group(1) if summary_match else "(no summary)"
                lines.append(f"- **{sf.stem}**: {summary}")

            lines.append(f"\n*Use `memory_get` with an epoch to read full session content.*")
            return Response(message="\n".join(lines), break_loop=False)

        except Exception as e:
            return Response(message=f"Failed to list sessions: {e}", break_loop=False)

    @staticmethod
    def _total_count(memory_dir: Path) -> int:
        return sum(1 for f in memory_dir.glob("*.md") if f.stem.isdigit() and 9 <= len(f.stem) <= 10)
