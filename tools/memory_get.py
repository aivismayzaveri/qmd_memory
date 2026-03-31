from helpers.tool import Tool, Response
from helpers import plugins
from pathlib import Path

from usr.plugins.qmd_memory.helpers import qmd_client


MAX_OUTPUT_CHARS = 8000


class MemoryGet(Tool):

    async def execute(self, session="", pattern="", max_lines=0, from_line=0, **kwargs) -> Response:
        """
        Retrieve full session content by epoch, docid, path, or glob pattern.

        Modes:
          - Single session: provide `session` (epoch like "1774702399", docid like "#abc123", or filename)
          - Batch by pattern: provide `pattern` (glob like "17747*.md" for a date range)
          - Line-range: use `max_lines` and `from_line` to read a specific section
        """
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not session and not pattern:
            return Response(
                message="Provide `session` (epoch/docid/filename) or `pattern` (glob like '17747*.md').",
                break_loop=False,
            )

        try:
            max_lines = int(max_lines)
        except (ValueError, TypeError):
            max_lines = 0
        try:
            from_line = int(from_line)
        except (ValueError, TypeError):
            from_line = 0

        memory_dir = Path(config.get("memory_dir", "/a0/usr/memory"))

        try:
            if pattern:
                # Batch retrieval: qmd multi-get "<pattern>" --full
                content = qmd_client.multi_get(pattern, config)
                if not content:
                    return Response(message=f"No documents matched pattern: `{pattern}`", break_loop=False)
                label = f"Documents matching `{pattern}`"

            elif max_lines > 0 or from_line > 0:
                # Line-range retrieval: qmd get <path> --full -l N --from N
                path = self._resolve_path(session, memory_dir)
                content = qmd_client.get_document_section(path, config, max_lines=max_lines, from_line=from_line)
                if not content:
                    return Response(message=f"Session `{session}` not found or empty.", break_loop=False)
                label = f"Session `{session}` (lines {from_line or 1}–{(from_line or 1) + max_lines - 1 if max_lines else 'end'})"

            else:
                # Full single document: qmd get <path> --full
                path = self._resolve_path(session, memory_dir)
                content = qmd_client.get_document(path, config)
                if not content:
                    # Fallback to direct filesystem read
                    content = self._read_from_disk(session, memory_dir)
                if not content:
                    return Response(message=f"Session `{session}` not found.", break_loop=False)
                label = f"Session `{session}`"

            # Truncate if needed
            if len(content) > MAX_OUTPUT_CHARS:
                content = content[:MAX_OUTPUT_CHARS] + f"\n\n... (truncated at {MAX_OUTPUT_CHARS} chars — use `max_lines`/`from_line` to paginate)"

            return Response(message=f"## {label}\n\n{content}", break_loop=False)

        except Exception as e:
            return Response(message=f"Failed to retrieve session: {e}", break_loop=False)

    @staticmethod
    def _resolve_path(session: str, memory_dir: Path) -> str:
        """Resolve session identifier to a QMD-compatible path."""
        # Docid format: #abc123 — pass directly to qmd get
        if session.startswith("#"):
            return session
        # Bare epoch: add .md suffix
        if session.isdigit() and 9 <= len(session) <= 10:
            return f"{session}.md"
        # Already has extension or path separator
        return session

    @staticmethod
    def _read_from_disk(session: str, memory_dir: Path) -> str:
        """Fallback: read session file directly from disk."""
        candidates = [
            memory_dir / session,
            memory_dir / f"{session}.md",
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""
