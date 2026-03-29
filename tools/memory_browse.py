from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import memory_files


MAX_BROWSE_CHARS = 5000


class MemoryBrowse(Tool):

    async def execute(self, category="", section="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        valid_categories = ["entities", "episodes", "facts", "procedure", "goals", "guardrails", "sessions", "knowledge", "docs"]
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
                    import re
                    summary_match = re.search(r'^summary:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
                    summary = summary_match.group(1) if summary_match else "(no summary)"
                    lines.append(f"- **{sf.stem}**: {summary}")
                result = "\n".join(lines)
            elif category == "docs":
                # List imported documents
                from pathlib import Path
                docs_dir = Path(memory_dir) / "docs"
                if not docs_dir.exists():
                    return Response(message="No documents imported yet.", break_loop=False)
                if section:
                    # Read a specific doc file
                    doc_file = docs_dir / section
                    if not doc_file.exists():
                        doc_file = docs_dir / f"{section}.md"
                    if doc_file.exists():
                        result = doc_file.read_text(encoding="utf-8")
                    else:
                        return Response(message=f"Document '{section}' not found in docs/", break_loop=False)
                else:
                    # List all docs from _index.md
                    idx = docs_dir / "_index.md"
                    if idx.exists():
                        result = idx.read_text(encoding="utf-8")
                    else:
                        doc_files = sorted(docs_dir.glob("*.md"))
                        lines = ["# Imported Documents\n"]
                        for df in doc_files:
                            if df.name != "_index.md":
                                lines.append(f"- {df.name}")
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
