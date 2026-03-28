# QMD Memory System

A persistent, file-based memory plugin for Agent Zero. Every conversation is automatically summarized and stored as human-readable markdown files. Memories are recalled during future conversations using hybrid search (text + semantic).

---

## How It Works — Simple Overview

```
Conversation starts
      │
      ▼
[INIT] Ensure memory files exist, register with QMD search engine
      │
      ▼
[RECALL] Every few messages, search memory for relevant context → inject into agent's prompt
      │
      ▼
Agent does its work...
      │
      ▼
[EXTRACT] At end of conversation, LLM extracts structured memories and saves them to files
      │
      ▼
[REINDEX] QMD reindexes the updated files in the background
```

---

## Memory Storage

All memories are stored as plain markdown files at `/a0/usr/memory/`:

| File / Folder | What it stores |
|---|---|
| `Episodes.md` | Timeline events — things that happened |
| `Facts.md` | User preferences, project info, links/references |
| `Knowledge.md` | Long-form reference content and documentation |
| `Procedure.md` | Step-by-step solutions that worked |
| `Goals.md` | Active and completed tasks |
| `Guardrails.md` | Behavioral rules injected into every system prompt |
| `entities/` | People, organizations, projects, technologies, places |
| `sessions/` | One summarized log per conversation |
| `docs/` | Externally imported documents (.pdf, .html, .md, etc.) |

Each file uses markdown `## Heading` entries with YAML frontmatter for metadata.

---

## Flow in Detail

### 1. Initialization (`monologue_start`)
When a conversation starts:
- Creates any missing memory files and directories
- Registers the memory folder as a QMD collection (if not already)
- Triggers a background reindex so new files are searchable

### 2. Recall (every N messages)
During the conversation, on a configurable interval (default: every 3 iterations):
- Takes the current message + recent history as a query
- Optionally uses a utility LLM to optimize the search query
- Runs a **hybrid QMD search** (BM25 full-text + semantic embeddings)
- Applies **temporal decay** — recent memories score higher
- Applies **MMR filtering** — removes near-duplicate results to save token space
- Injects the top results into the agent's context as `# Recalled Memories`

### 3. Extraction (`monologue_end`)
At the end of each conversation (if it meets minimum size thresholds):
- Passes the full conversation history to a utility LLM
- LLM extracts structured data across all categories (entities, episodes, facts, etc.)
- Each category is deduplicated before saving:
  - **Entities** — matched by name; merged if already exists
  - **Episodes** — matched by title; updated or appended
  - **Facts** — similarity-checked via QMD (score > 0.85 = update, else append)
  - **Goals** — tracked as Active / Completed; updated if already present
- A session log is saved to `sessions/<epoch>.md` with a summary and backlinks
- If any file exceeds 500 lines, it is auto-split into a subdirectory

### 4. Guardrails (`system_prompt`)
On every turn:
- Reads `Guardrails.md`
- Injects its contents at the top of the system prompt so behavioral rules are always active

---

## Agent Tools

The agent can also interact with memory manually using these tools:

| Tool | What it does |
|---|---|
| `memory_search` | Search memories with a query; returns scored results |
| `memory_save` | Save new information to a specific category |
| `memory_update` | Update an existing memory entry by heading |
| `memory_browse` | Read an entire category or section |
| `memory_import` | Import an external file (PDF, HTML, CSV, etc.) into the docs collection |
| `guardrails_update` | Add or modify behavioral rules in Guardrails.md |

---

## Search Engine (QMD)

QMD (`@tobilu/qmd`) is a local Node.js search engine that combines:
- **BM25** — classic keyword/full-text ranking
- **Semantic embeddings** — meaning-based similarity

Results are further post-processed by:
- **Temporal decay** — older memories get a lower score (`score × e^(−λ × days_old)`, half-life configurable, default 30 days)
- **MMR (Maximal Marginal Relevance)** — reranks results to balance relevance with diversity, preventing 5 near-identical snippets eating your token budget

The QMD engine runs as a local CLI (`node qmd.js`) called via subprocess. All calls degrade gracefully — if QMD fails, memory recall returns empty rather than crashing the agent.

---

## Key Configuration (`default_config.yaml`)

| Setting | Default | Description |
|---|---|---|
| `memory_dir` | `/a0/usr/memory` | Where memory files are stored |
| `memory_recall_interval` | `3` | Recall every N agent iterations |
| `memory_recall_max_results` | `8` | Max memories injected per recall |
| `memory_recall_token_budget` | `3000` | Max tokens for recalled memories |
| `memory_extract_min_chars` | `200` | Min user chars to trigger extraction |
| `memory_extract_min_tool_calls` | `2` | Min tool calls to trigger extraction |
| `memory_temporal_decay_halflife_days` | `30` | How fast old memories decay in ranking |
| `memory_mmr_lambda` | `0.7` | Relevance vs. diversity balance (1.0 = pure relevance) |
| `memory_per_agent` | `false` | Give each sub-agent its own memory folder |
| `auto_split_threshold_lines` | `500` | Split large files into subdirectories at this size |
| `guardrails_enabled` | `true` | Inject Guardrails.md into every system prompt |

---

## Files & Structure

```
qmd_memory/
├── plugin.yaml                  # Plugin metadata and registration
├── default_config.yaml          # All configurable settings with defaults
├── hooks.py                     # install / uninstall lifecycle hooks
├── execute.py                   # Manual setup & reindex script (run from plugin UI)
├── __init__.py
│
├── extensions/python/
│   ├── monologue_start/
│   │   └── _10_qmd_memory_init.py       # Initialization on conversation start
│   ├── message_loop_prompts_after/
│   │   ├── _50_recall_memories.py       # Memory recall injection
│   │   ├── _80_precompact_check.py      # Warn agent before context compaction
│   │   └── _91_recall_wait.py           # Wait for async search to complete
│   ├── monologue_end/
│   │   └── _50_extract_memories.py      # Memory extraction at conversation end
│   └── system_prompt/
│       └── _20_guardrails_prompt.py     # Inject Guardrails.md into system prompt
│
├── tools/
│   ├── memory_search.py
│   ├── memory_save.py
│   ├── memory_update.py
│   ├── memory_browse.py
│   ├── memory_import.py
│   └── guardrails_update.py
│
├── helpers/
│   ├── memory_files.py          # All file I/O (atomic writes, dedup, split logic)
│   ├── qmd_client.py            # QMD CLI wrapper (search, reindex, collection mgmt)
│   └── session_log.py           # Session summary creation
│
├── api/
│   ├── search.py                # POST /api/plugins/qmd_memory/search
│   ├── index.py                 # POST /api/plugins/qmd_memory/index
│   └── status.py                # POST /api/plugins/qmd_memory/status
│
├── prompts/
│   ├── extraction.system.md     # LLM prompt defining memory extraction schema
│   ├── extraction.message.md    # Template: passes conversation history to LLM
│   ├── agent.system.memories.md # Template for injecting recalled memories
│   ├── agent.system.guardrails.md # Template for injecting guardrails
│   ├── agent.system.tool.qmd_memory.md  # Tool docs shown to the agent
│   └── ...                      # Other response/confirmation templates
│
└── qmd_engine/                  # Local QMD installation (node_modules)
```

---

## Setup & Manual Reindex

On first install, `hooks.py` installs the QMD CLI via npm and creates the memory directory structure.

To manually re-run setup or force a full reindex, run `execute.py` from the Agent Zero plugin execution UI. It will:
1. Verify the QMD CLI is installed
2. Create any missing memory directories
3. Register the memory folder as a QMD collection
4. Run a full reindex of all files
