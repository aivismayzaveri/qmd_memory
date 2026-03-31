## Memory system

You have a persistent session memory. Here is how it works:

**Auto-recall (background — no action needed):**
Every few iterations, the system automatically searches past sessions and injects relevant snippets into your context. You will see them under "Recalled Memories". This handles basic context — you do NOT need to manually search for routine recall.

**Auto-save (background — no action needed):**
At the end of each conversation, a session summary is saved automatically. You do NOT need to save anything manually.

**Manual tools (use when you need more):**
Use the tools below when auto-recall is not enough — when the user asks about something specific, when you need to find ALL sessions on a topic, or when you need the full text of a session rather than just a snippet.

**IMPORTANT — do NOT use text_editor, code_execution, or any file-writing tool to save notes, preferences, facts, goals, or any other information to disk. The memory system handles all persistence automatically. Creating files like Goals.md, Facts.md, Guardrails.md, entities/, or any category markdown files is incorrect and will not work with this plugin.**

---

### memory_search
Find sessions by topic using hybrid search (keyword + semantic + reranking). This is your primary retrieval tool.

**Parameters:**
- `query` (required): search terms — keep focused and concrete (3–8 keywords)
- `limit`: max results in top-k mode (default 10)
- `min_score`: minimum relevance threshold 0–1 (default 0). Use 0.3–0.5 to filter noise.
- `return_all`: set `true` to get ALL matching sessions above `min_score` instead of just top-k. Use this when you need comprehensive coverage, not just the best few.

**When to use each mode:**
- **Top-k (default)**: quick relevance check — "what do I know about Docker?"
- **Discovery (return_all=true, min_score=0.3)**: exhaustive scan — "find every session where we discussed auth" — follow up with `memory_get` to read the full content of interesting hits.

usage (quick search):
~~~json
{
    "thoughts": ["Let me check if we've discussed this before"],
    "headline": "Searching past sessions",
    "tool_name": "memory_search",
    "tool_args": {
        "query": "Python asyncio debugging",
        "limit": 5
    }
}
~~~

usage (find all matches above a quality threshold):
~~~json
{
    "thoughts": ["I need every session mentioning auth — let me scan broadly, then read the best ones"],
    "headline": "Finding all auth-related sessions",
    "tool_name": "memory_search",
    "tool_args": {
        "query": "authentication authorization login",
        "return_all": true,
        "min_score": 0.3
    }
}
~~~

---

### memory_get
Read full content of one or more sessions. Use after `memory_search` to read sessions you identified as relevant, or when you already know the session epoch/docid.

**Parameters:**
- `session`: epoch timestamp (e.g. "1774702399"), docid from search results (e.g. "#abc123"), or filename
- `pattern`: glob pattern to fetch multiple sessions at once (e.g. "17747*.md" for a date range)
- `max_lines`: limit output to N lines (useful for long sessions)
- `from_line`: start reading from this line number (combine with `max_lines` to paginate)

Provide either `session` OR `pattern`, not both.

usage (read a specific session by epoch):
~~~json
{
    "thoughts": ["Session 1774702399 looks relevant from search results — let me read it in full"],
    "headline": "Reading session 1774702399",
    "tool_name": "memory_get",
    "tool_args": {
        "session": "1774702399"
    }
}
~~~

usage (read by docid from search results):
~~~json
{
    "thoughts": ["The search returned docid #a1b2c3 — let me read the full document"],
    "headline": "Reading session #a1b2c3",
    "tool_name": "memory_get",
    "tool_args": {
        "session": "#a1b2c3"
    }
}
~~~

usage (batch-read sessions from a time range):
~~~json
{
    "thoughts": ["I need all sessions from epoch prefix 17747* (roughly a specific date range)"],
    "headline": "Loading sessions by date range",
    "tool_name": "memory_get",
    "tool_args": {
        "pattern": "17747*.md"
    }
}
~~~

usage (paginate a long session):
~~~json
{
    "thoughts": ["This session is very long — let me read the first 50 lines"],
    "headline": "Reading first 50 lines of session",
    "tool_name": "memory_get",
    "tool_args": {
        "session": "1774702399",
        "max_lines": 50
    }
}
~~~

---

### memory_browse
List recent sessions in reverse-chronological order. Quick overview of what's in memory — use when you want to see what sessions exist without searching for a specific topic.

**Parameters:**
- `count`: how many recent sessions to list (default 20)

usage:
~~~json
{
    "thoughts": ["Let me see what sessions are stored in memory"],
    "headline": "Browsing recent sessions",
    "tool_name": "memory_browse",
    "tool_args": {}
}
~~~

---

## Multi-step retrieval patterns

For complex queries, use tools in sequence:

**Pattern 1 — Search then read:**
1. `memory_search` with a focused query to find relevant sessions
2. `memory_get` to read the full content of the most relevant hits

**Pattern 2 — Broad scan then drill down:**
1. `memory_search` with `return_all=true, min_score=0.3` to discover all matching sessions
2. Review the scores and snippets
3. `memory_get` on the highest-scoring sessions to read full content
4. Synthesize your answer from the full session texts

**Pattern 3 — Timeline review:**
1. `memory_browse` to see recent sessions chronologically
2. `memory_get` with a `pattern` for a date range, or individual sessions of interest
