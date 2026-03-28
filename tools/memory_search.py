import os

from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import qmd_client


class MemorySearch(Tool):

    async def execute(self, query="", limit=10, category="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not query:
            return Response(message="Please provide a search query.", break_loop=False)

        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10

        results = qmd_client.search(str(query), config, limit=limit)

        if not results:
            return Response(
                message=f"No memories found for: {query}",
                break_loop=False,
            )

        # Filter by category if specified
        if category:
            category_lower = category.lower()
            results = [
                r for r in results
                if category_lower in r.get("path", "").lower()
                or category_lower in r.get("title", "").lower()
            ]
            if not results:
                return Response(
                    message=f"No memories found in category '{category}' for: {query}",
                    break_loop=False,
                )

        # Format results
        lines = [f"Found {len(results)} result(s) for: **{query}**\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            path = r.get("path", "")
            score = r.get("score", 0)
            snippet = r.get("snippet", "")

            basename = os.path.basename(path)
            parent = os.path.basename(os.path.dirname(path))
            cat_label = parent if parent in ("entities", "sessions") else os.path.splitext(basename)[0]

            lines.append(f"### {i}. {title} [{cat_label}]")
            lines.append(f"**Score:** {score:.3f} | **File:** `{basename}`")
            if snippet:
                snippet_short = snippet[:300] + "..." if len(snippet) > 300 else snippet
                lines.append(f"\n{snippet_short}")
            lines.append("")

        return Response(message="\n".join(lines), break_loop=False)
