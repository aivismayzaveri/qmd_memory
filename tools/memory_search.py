import os

from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import qmd_client


# Canonical category names and their aliases (singular, plural, common typos)
_CATEGORY_ALIASES: dict[str, str] = {
    # entities
    "entity": "entities",
    "entities": "entities",
    "people": "entities",
    "person": "entities",
    # facts
    "fact": "facts",
    "facts": "facts",
    # episodes
    "episode": "episodes",
    "episodes": "episodes",
    "events": "episodes",
    "event": "episodes",
    # goals
    "goal": "goals",
    "goals": "goals",
    "tasks": "goals",
    "task": "goals",
    # knowledge
    "knowledge": "knowledge",
    "knowledgebase": "knowledge",
    "kb": "knowledge",
    # procedure
    "procedure": "procedure",
    "procedures": "procedure",
    "how-to": "procedure",
    "howto": "procedure",
    # guardrails
    "guardrail": "guardrails",
    "guardrails": "guardrails",
    "rules": "guardrails",
    "rule": "guardrails",
    # sessions
    "session": "sessions",
    "sessions": "sessions",
    # docs
    "doc": "docs",
    "docs": "docs",
    "document": "docs",
    "documents": "docs",
}

# Folder-based categories (stored as files inside a subdirectory)
_FOLDER_CATEGORIES = {"entities", "sessions", "docs"}


def _normalize_category(cat: str) -> str:
    return _CATEGORY_ALIASES.get(cat.lower().strip(), cat.lower().strip())


def _path_from_result(r: dict) -> str:
    """Return the file path from a QMD result, stripping the qmd:// scheme."""
    raw = r.get("path", r.get("file", ""))
    if raw.startswith("qmd://"):
        return raw[6:]  # "memory/entities/people.md"
    return raw


def _cat_label(path: str) -> str:
    """Derive a human-readable category label from a file path."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if len(parts) >= 2 and parts[-2] in _FOLDER_CATEGORIES:
        return parts[-2]            # "entities", "sessions", "docs"
    if parts:
        return parts[-1].rsplit(".", 1)[0]  # "Facts", "Goals", etc.
    return "memory"


def _matches_category(path: str, category: str) -> bool:
    """
    Return True if the result at `path` belongs to `category`.

    path is already stripped of the qmd:// prefix (e.g. "memory/entities/people.md").
    category is a user-supplied string (e.g. "entities", "entity", "facts").
    """
    cat = _normalize_category(category)
    path_lower = path.lower()

    if cat in _FOLDER_CATEGORIES:
        # Match files inside the folder: "…/entities/…"
        return f"/{cat}/" in f"/{path_lower}/"

    # File-based categories: match filename stem exactly or with a numeric suffix
    # e.g. "facts" matches "facts.md", "facts_2.md"
    stem = path_lower.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stem == cat or stem.startswith(f"{cat}_") or stem.startswith(f"{cat}-")


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
        # When a category is specified we use a two-pass strategy:
        #
        #   Pass 1 — search with an expanded limit (3×) so that category-specific
        #            files that didn't rank in the global top-N are still captured.
        #
        #   Pass 2 (fallback) — if pass 1 yields no matches after filtering,
        #            prepend the category name to the query to bias QMD toward
        #            that category and search again.
        #
        # Without this, a post-filter on the global top-10 silently returns
        # nothing whenever the most relevant file happened to rank outside that set.

        if category:
            cat_canonical = _normalize_category(category)
            expanded_limit = limit * 3

            # Pass 1
            results = qmd_client.search(normalized_query, config, limit=expanded_limit)
            filtered = [r for r in results if _matches_category(_path_from_result(r), category)]

            # Pass 2 — category-biased fallback
            if not filtered:
                biased_query = f"{cat_canonical} {normalized_query}"
                fallback = qmd_client.search(biased_query, config, limit=expanded_limit)
                filtered = [r for r in fallback if _matches_category(_path_from_result(r), category)]

            results = filtered[:limit]
        else:
            results = qmd_client.search(normalized_query, config, limit=limit)

        # ── No results ────────────────────────────────────────────────────
        if not results:
            hint = f" (searched: `{normalized_query}`)" if normalized_query != raw_query else ""
            cat_hint = f" in category '{category}'" if category else ""
            return Response(
                message=f"No memories found{cat_hint} for: {raw_query}{hint}",
                break_loop=False,
            )

        # ── Format results ────────────────────────────────────────────────
        query_label = (
            f"**{raw_query}**"
            + (f" → `{normalized_query}`" if normalized_query != raw_query else "")
        )
        cat_label_header = f" in `{_normalize_category(category)}`" if category else ""
        lines = [f"Found {len(results)} result(s) for: {query_label}{cat_label_header}\n"]

        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            path = _path_from_result(r)
            score = r.get("score", 0)
            snippet = r.get("snippet", "")

            cat = _cat_label(path)
            basename = path.rsplit("/", 1)[-1]

            lines.append(f"### {i}. {title} [{cat}]")
            lines.append(f"**Score:** {score:.3f} | **File:** `{basename}`")
            if snippet:
                snippet_short = snippet[:300] + "..." if len(snippet) > 300 else snippet
                lines.append(f"\n{snippet_short}")
            lines.append("")

        return Response(message="\n".join(lines), break_loop=False)
