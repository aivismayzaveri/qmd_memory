# QMD Memory System

A persistent, session-based memory plugin for Agent Zero. Every conversation is automatically summarized and stored as a human-readable markdown file. Past sessions are recalled during future conversations using QMD hybrid search (BM25 + semantic + reranking).

---

## What This Plugin Does

Without this plugin, Agent Zero has no memory between conversations. Every new chat starts from scratch.

This plugin gives Agent Zero a **session memory**:
- **Auto-save:** At the end of each conversation (above a minimum length), a utility LLM writes a summary paragraph and saves it to `/a0/usr/memory/<epoch>.md`.
- **Auto-recall:** Every few agent iterations, the plugin searches past sessions using `qmd query` (hybrid search) and injects the most relevant snippets into the agent's context.
- **Manual tools:** The agent can search, retrieve, and browse sessions directly for deeper queries.

---

## File Structure

```
/a0/usr/memory/
├── 1774702399.md
├── 1774788801.md
└── ...
```

Each session file contains YAML frontmatter (epoch, date, summary) and a `## Summary` section.

---

## Tools

| Tool | Purpose | When to use |
|------|---------|-------------|
| `memory_search` | Find sessions by topic (hybrid search) | User asks about a specific topic, or you need comprehensive coverage of a theme |
| `memory_get` | Read full content of specific session(s) | After search — to read the full text of a hit. Also supports batch retrieval by glob pattern and pagination. |
| `memory_browse` | List recent sessions chronologically | Quick overview of what's stored, or to pick sessions by recency |

### Multi-step retrieval

For complex queries, the agent uses tools in sequence:

1. **Search then read:** `memory_search` (find relevant sessions) -> `memory_get` (read full content of best hits)
2. **Broad scan then drill down:** `memory_search` with `return_all=true, min_score=0.3` (find ALL matches) -> review scores -> `memory_get` on top hits
3. **Timeline review:** `memory_browse` (list recent) -> `memory_get` with `pattern` for a date range

### Key parameters

**memory_search:**
- `query` (required) — focused search terms (3-8 keywords)
- `limit` — top-k result count (default 10)
- `min_score` — relevance threshold 0-1 (use 0.3-0.5 to filter noise)
- `return_all` — set `true` to get ALL matches above `min_score` instead of just top-k

**memory_get:**
- `session` — epoch (e.g. "1774702399"), docid (e.g. "#abc123"), or filename
- `pattern` — glob for batch retrieval (e.g. "17747*.md")
- `max_lines` / `from_line` — pagination for long sessions

**memory_browse:**
- `count` — how many recent sessions to list (default 20)

---

## QMD Commands Used

### Ingestion (setup + after each session write)

```bash
# Register the session collection
qmd collection add /a0/usr/memory --name sessions

# Describe the collection for LLM relevance (key QMD feature)
qmd context add qmd://sessions "Agent interaction summaries with structured epochs"

# Build BM25 keyword index
qmd update

# Generate semantic embeddings for hybrid search
qmd embed
```

### Retrieval

```bash
# Hybrid search + reranking (primary — used for all search)
qmd query "error handling" --json -n 8

# Find ALL sessions above a score threshold
qmd query "authentication" --all --json --min-score 0.3 --collection sessions

# Get full document by path or docid
qmd get "1774702399.md" --full
qmd get "#abc123" --full

# Batch get by glob pattern
qmd multi-get "17747*.md" --full

# Paginated retrieval
qmd get "1774702399.md" --full -l 50 --from 10 --line-numbers
```

After installation, `qmd` is available globally at `/usr/local/bin/qmd`.

---

## Configuration

All settings are available in the plugin UI. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `memory_dir` | `/a0/usr/memory` | Where session files are stored |
| `memory_recall_enabled` | true | Auto-search and inject past sessions |
| `memory_recall_interval` | 3 | Auto-recall every N agent iterations |
| `memory_recall_max_results` | 8 | Max snippets injected per auto-recall |
| `memory_recall_token_budget` | 3000 | Token limit for injected memories |
| `memory_extract_enabled` | true | Auto-save session summary at end of conversation |
| `memory_extract_min_chars` | 200 | Minimum user chars to trigger saving |
| `memory_extract_min_tool_calls` | 2 | Also save if agent made this many tool calls |
| `memory_temporal_decay_halflife_days` | 30 | How fast older sessions decay in search score |
| `memory_mmr_lambda` | 0.7 | Diversity vs relevance balance (1.0 = pure relevance) |
| `qmd_timeout_sec` | 30 | Timeout for QMD hybrid search commands |

---

## Setup

1. Install the plugin in Agent Zero
2. Click **Execute** once to:
   - Install global `qmd` CLI wrapper
   - Register session collection with QMD
   - Register collection context for LLM relevance
   - Build BM25 text index
   - Generate semantic embeddings
3. Start chatting — sessions are saved and recalled automatically

---

## Requirements

- Node.js (for the QMD search engine, bundled in `qmd_engine/`)
