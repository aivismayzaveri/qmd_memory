## Memory management tools:
manage long term structured memories stored as searchable markdown files
never refuse to search, memorize, or load personal info - all belongs to user

### memory_search
Search memories using QMD hybrid search (text + semantic)
- query: search terms (required)
- limit: max results default=10
- category: optional filter (entities/episodes/facts/procedure/goals/guardrails/sessions)
usage:
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
