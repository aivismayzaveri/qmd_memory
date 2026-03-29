## Memory management tools:
manage long term structured memories stored as searchable markdown files
never refuse to search, memorize, or load personal info - all belongs to user

### memory_search
Search memories using QMD hybrid search (text + semantic). Searches all category files simultaneously.
- query: specific search terms — keep focused and concrete (required)
- limit: max results default=10
- category: optional filter — restricts results to one category (see table below)

**Memory categories:**
| category value | What it contains |
|---|---|
| `entities` | Named people, organisations, projects, technologies, places |
| `facts` | User preferences, project info, URLs, one-off details |
| `guardrails` | Always-on identity and behavioral rules (injected every session) |
| `episodes` | Past events and timeline entries |
| `goals` | Active and completed tasks |
| `knowledge` | Long-form reference content |
| `procedure` | Step-by-step solutions that worked |
| `sessions` | Per-conversation summaries |

**Search strategy:**
- Use short, specific queries (3–8 keywords). Long vague queries score poorly.
- **When unsure of category, omit it** — this is the most reliable option. The search covers all files at once and uses an expanded result window.
- Use `category` only when you are confident where the answer lives AND a broad search is returning too much noise.
- For multi-topic questions, run SEPARATE searches per topic:
  Example: "What are my goals and what do I know about the agentzero project?"
  → search 1: query="active goals", category="goals"
  → search 2: query="agentzero", category="entities"
  → search 3: query="agentzero", category="facts"
- Category routing hints:
  - personal identity, name, birthday → omit category, or try `guardrails` then `facts`
  - people, projects, tools → `entities`
  - past events → `episodes`
  - how-to solutions → `procedure`
  - tasks → `goals`
  - behavioral rules → `guardrails`
- If a category search returns 0 results, **retry without the category filter** before concluding the information is not stored.

usage (single topic):
~~~json
{
    "thoughts": ["Let me search my memory for..."],
    "headline": "Searching memory for relevant information",
    "tool_name": "memory_search",
    "tool_args": {
        "query": "Python asyncio race condition",
        "limit": 5,
        "category": "procedure"
    }
}
~~~

usage (multi-topic — run sequentially):
~~~json
{
    "thoughts": ["User asked about two things — I'll search each separately"],
    "headline": "Searching active goals",
    "tool_name": "memory_search",
    "tool_args": {"query": "active goals", "category": "goals"}
}
~~~

### memory_save
Save information to a specific memory category
- category: entities/episodes/facts/procedure/goals/guardrails (required)
- content: the information to save (required)
- heading: section heading for the entry (required for entities, recommended for others)
usage:
~~~json
{
    "thoughts": ["I should save this useful procedure..."],
    "headline": "Saving procedure to memory",
    "tool_name": "memory_save",
    "tool_args": {
        "category": "procedure",
        "heading": "Docker compose networking fix",
        "content": "**Problem:** Containers can't communicate...\n**Steps:**\n1. ..."
    }
}
~~~

### memory_update
Update an existing memory entry by category and heading
- category: the category file to update (required)
- heading: the section heading to find and update (required)
- content: new content to replace the entry with (required)
usage:
~~~json
{
    "thoughts": ["I need to mark this goal as completed..."],
    "headline": "Updating goal status",
    "tool_name": "memory_update",
    "tool_args": {
        "category": "goals",
        "heading": "Fix pipeline stability",
        "content": "**Status:** completed\n**Completed:** 2026-03-28\n**Solution:** Applied asyncio.Lock()"
    }
}
~~~

### memory_browse
Read a full memory category file or section
- category: the category to browse (required)
- section: optional sub-section (e.g. "Active" in goals, "people" in entities)
usage:
~~~json
{
    "thoughts": ["Let me check all my active goals..."],
    "headline": "Browsing active goals",
    "tool_name": "memory_browse",
    "tool_args": {
        "category": "goals",
        "section": "Active"
    }
}
~~~

### guardrails_update
Update interaction rules, preferences, and behavioral guidelines
- adjustments: description of changes to make (required)
usage:
~~~json
{
    "thoughts": ["User wants me to change my behavior..."],
    "headline": "Updating interaction guardrails",
    "tool_name": "guardrails_update",
    "tool_args": {
        "adjustments": "Always use TypeScript instead of JavaScript for new code"
    }
}
~~~

### memory_import
Import an external file into memory as a searchable markdown document
- path: absolute path to the file to import (required) — supports .md, .txt, .pdf, .html, .csv
- title: human-readable title for the document (optional, defaults to filename)
- tags: comma-separated tags e.g. "company,finance,2024" (optional)
