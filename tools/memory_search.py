from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import qmd_client


class MemorySearch(Tool):

    async def execute(self, query="", limit=10, min_score=0, return_all=False, **kwargs) -> Response:
        """
        Search past sessions using hybrid search (qmd query).

        Modes:
          - Top-k (default): returns the best N results. Good for "what do I know about X?"
          - Discovery (return_all=true): returns ALL sessions above min_score.
            Good for "find every session mentioning X" before reading specific ones with memory_get.
        """
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not query:
            return Response(message="Please provide a search query.", break_loop=False)

        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10

        try:
            min_score = float(min_score)
        except (ValueError, TypeError):
            min_score = 0

        # Coerce return_all from string if needed (tool args may arrive as strings)
        if isinstance(return_all, str):
            return_all = return_all.lower() in ("true", "1", "yes")

        # ── Query normalization ───────────────────────────────────────────
        raw_query = str(query)
        normalized_query = raw_query
        if config.get("memory_search_query_prep", True):
            try:
                system = self.agent.read_prompt("search.query.sys.md")
                normalized = await self.agent.call_utility_model(
                    system=system,
                    message=raw_query,
                )
                if normalized and isinstance(normalized, str) and normalized.strip():
                    normalized_query = normalized.strip()
            except Exception:
                pass  # Graceful fallback to raw query

        # ── Retrieval ─────────────────────────────────────────────────────
        if return_all:
            # Discovery mode: qmd query --all --json --min-score --collection sessions
            results = qmd_client.search_all(normalized_query, config, min_score=min_score)
        else:
            # Top-k mode: qmd query --json -n <limit>
            results = qmd_client.search(normalized_query, config, limit=limit)
            if min_score > 0:
                results = [r for r in results if r.get("score", 0) >= min_score]

        # ── No results ────────────────────────────────────────────────────
        if not results:
            hint = f" (searched: `{normalized_query}`)" if normalized_query != raw_query else ""
            score_hint = f" above score {min_score}" if min_score > 0 else ""
            return Response(
                message=f"No sessions found{score_hint} for: {raw_query}{hint}",
                break_loop=False,
            )

        # ── Format results ────────────────────────────────────────────────
        query_label = (
            f"**{raw_query}**"
            + (f" -> `{normalized_query}`" if normalized_query != raw_query else "")
        )
        mode_label = f" (all above {min_score})" if return_all else f" (top {limit})"
        lines = [f"Found {len(results)} session(s) for: {query_label}{mode_label}\n"]

        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            path = _path_from_result(r)
            score = r.get("score", 0)
            snippet = r.get("snippet", "")
            docid = r.get("docid", "")

            basename = path.rsplit("/", 1)[-1]
            stem = basename.rsplit(".", 1)[0]
            epoch_label = stem if (stem.isdigit() and 9 <= len(stem) <= 10) else basename

            lines.append(f"### {i}. {title}")
            id_part = f" | **DocID:** `{docid}`" if docid else ""
            lines.append(f"**Score:** {score:.3f} | **Session:** `{epoch_label}`{id_part}")
            if snippet:
                snippet_short = snippet[:300] + "..." if len(snippet) > 300 else snippet
                lines.append(f"\n{snippet_short}")
            lines.append("")

        if return_all and len(results) > 5:
            lines.append(f"\n*Use `memory_get` with a session epoch or docid to read full content.*")

        return Response(message="\n".join(lines), break_loop=False)


def _path_from_result(r: dict) -> str:
    """Return the file path from a QMD result, stripping the qmd:// scheme."""
    raw = r.get("path", r.get("file", ""))
    if raw.startswith("qmd://"):
        return raw[6:]
    return raw
