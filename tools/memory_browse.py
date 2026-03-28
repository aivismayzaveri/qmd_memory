from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import memory_files


MAX_BROWSE_CHARS = 5000


class MemoryBrowse(Tool):

    async def execute(self, category="", section="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        valid_categories = ["entities", "episodes", "facts", "procedure", "goals", "guardrails", "sessions"]
        if not category:
            return Response(
                message=f"Please specify a category. Available: {', '.join(valid_categories)}",
                break_loop=False,
            )

        if category not in valid_categories:
            return Response(
                message=f"Invalid category '{category}'. Available: {', '.join(valid_categories)}",
                break_loop=False,
            )

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        try:
            if category == "sessions":
                # List recent sessions
                from pathlib import Path
                sessions_dir = Path(memory_dir) / "sessions"
                if not sessions_dir.exists():
                    return Response(message="No sessions recorded yet.", break_loop=False)
                session_files = sorted(sessions_dir.glob("*.md"), reverse=True)[:10]
                lines = ["# Recent Sessions\n"]
                for sf in session_files:
                    content = sf.read_text(encoding="utf-8")
                    # Extract summary from frontmatter
                    import re
                    summary_match = re.search(r'^summary:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
                    summary = summary_match.group(1) if summary_match else "(no summary)"
                    lines.append(f"- **{sf.stem}**: {summary}")
                result = "\n".join(lines)
            elif section:
                result = memory_files.read_category_raw(memory_dir, category, section)
            else:
                result = memory_files.read_category_raw(memory_dir, category)

            if not result or not result.strip():
                return Response(
                    message=f"Category '{category}' is empty.",
                    break_loop=False,
                )

            # Truncate if needed
            if len(result) > MAX_BROWSE_CHARS:
                result = result[:MAX_BROWSE_CHARS] + f"\n\n... (truncated at {MAX_BROWSE_CHARS} chars)"

        except Exception as e:
            return Response(message=f"Failed to browse memory: {e}", break_loop=False)

        return Response(message=result, break_loop=False)
