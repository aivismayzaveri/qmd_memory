# QMD Memory System

A persistent, file-based memory plugin for Agent Zero. Every conversation is automatically summarized and stored as human-readable markdown files. Memories are recalled during future conversations using hybrid search (text + semantic).

---

## Plain English Guide — What This Plugin Does and Why

### The problem it solves

Without this plugin, Agent Zero has **no memory between conversations**. Every time you start a new chat, it has forgotten everything — your name, your preferences, what you were working on, solutions you already found. You have to repeat yourself every single time.

This plugin gives Agent Zero a **permanent memory**. It remembers who you are, what you like, what you've done, and what you're working on — across every conversation, forever.

### How it works (no jargon)

Think of it like giving your AI assistant a **notebook** and a **search engine** for that notebook.

**Writing in the notebook:** At the end of every conversation, the plugin reads through what you talked about and pulls out the important bits. It organizes them into different sections — like having tabs in a real notebook:

- **People & Things** — names, projects, tools, companies you've mentioned
- **Facts** — your preferences, settings, URLs, things you've told it to remember
- **Rules** — things it should always do or never do (like "always use TypeScript" or "never push to main without asking")
- **Events** — what happened and when
- **Goals** — what you're trying to accomplish
- **How-Tos** — step-by-step solutions that worked
- **Knowledge** — longer reference material

**Reading from the notebook:** During every conversation, the plugin searches the notebook for anything relevant to what you're currently talking about. If you're discussing a project, it pulls up what it knows about that project. If you mention a person, it recalls who they are. This happens automatically in the background — you don't have to ask it to remember.

**The rules page:** There is a special file called Guardrails that gets loaded into *every single conversation* no matter what. This is where your identity (name, birthday), your preferences (tone, style), and your hard rules (security, code style) live. The agent literally cannot forget these — they're injected before it even starts thinking about your message.

### Why the files are plain markdown

All memories are stored as regular text files you can open and read yourself. There's no database, no binary format, nothing hidden. If the plugin stored a fact wrong, you can just open the file and fix it. If you want to see everything it knows about you, just browse the folder.

### How it avoids duplicates

When the plugin extracts a new piece of information, it checks if it already has something similar. For example, if you mentioned "Vismay" in one chat and "Vismay Zaveri" in another, it's smart enough to know that's the same person and updates the existing entry instead of creating a duplicate. It does this in three steps:

1. **Exact match** — is the name already there? (handles uppercase/lowercase differences)
2. **Fuzzy match** — is there something *close*? ("vismay" matches "Vismay Zaveri" because one is a subset of the other)
3. **AI match** (optional) — a small neural model that can catch things with no obvious text overlap, like matching a username "aivismayzaveri" to the person "Vismay Zaveri" by reading the stored description

Step 3 is off by default because it needs a ~230 MB model download. Steps 1 and 2 are always active and catch most cases.

### How search works

When the plugin searches for memories, it combines two approaches:

- **Keyword matching** — finds exact words and phrases (like a normal search engine)
- **Meaning matching** — understands that "date of birth" and "birthday" mean the same thing even though the words are different

It also prioritizes **recent** memories over old ones (something from yesterday scores higher than something from 6 months ago) and makes sure the results are **diverse** (it won't return 5 nearly identical snippets — it spreads across different topics).

### What "Execute" does

When you click the Execute button in the plugin settings, it runs a setup script that:

- Makes sure all the memory folders exist
- Tells the search engine about your memory files so they become searchable
- Installs any optional packages needed for full features (PDF import, fuzzy matching, etc.)
- If you've enabled the AI entity matcher, downloads that model

You only need to run this once after installing, or again if something seems broken.

### What you can configure

Everything is adjustable from the Agent Zero UI:

- How often it searches for relevant memories during a chat (every 3 messages by default)
- How many memories it injects (8 by default — more memories = more context but uses more tokens)
- Whether to use an AI to clean up search queries before searching
- How aggressive entity deduplication should be
- Whether to enable the optional AI-powered entity matcher
- Where the memory files are stored on disk

Most defaults work well out of the box. The main thing you might want to change is enabling GLinker if you find duplicate entities building up.

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
[EXTRACT] At end of conversation, LLM extracts structured memories and saves them
          to Episodes, Facts, Knowledge, Procedure, Goals, Entities, and Guardrails
      │
      ▼
[REINDEX] QMD reindexes the updated files in the background
```

---

## Memory Storage

All memories are stored as plain markdown files at `/a0/usr/memory/`:

| File / Folder | What it stores |
|---|---|
| `Guardrails.md` | **Always-on rules** — injected into every system prompt automatically |
| `Facts.md` | User preferences, project info, links/references |
| `Episodes.md` | Timeline events — things that happened |
| `Goals.md` | Active and completed tasks |
| `Knowledge.md` | Long-form reference content and documentation |
| `Procedure.md` | Step-by-step solutions that worked |
| `entities/` | People, organizations, projects, technologies, places |
| `sessions/` | One summarized log per conversation |
| `docs/` | Externally imported documents (.pdf, .html, .md, etc.) |

Each file uses markdown `## Heading` entries with YAML frontmatter for metadata.

### Guardrails.md sections

`Guardrails.md` has six named sections. The extraction LLM routes entries to the correct section automatically:

| Section | What goes here |
|---|---|
| `Identity` | User's full name, date of birth, pronouns, role — must be known in every session |
| `Interaction Preferences` | How the user likes responses — tone, verbosity, address style |
| `Code Style` | Language preferences, formatting rules, tools to always use or avoid |
| `Security` | Things never to do — no force push, no deleting without confirmation |
| `Reminders` | Persistent reminders to surface every session |
| `Other` | Any other permanent rules |

---

## Extraction Routing Guide

The LLM uses this routing table during extraction. **Cross-posting is intentional** — the same fact can and should appear in multiple categories.

| If the information is... | Route to |
|---|---|
| A named person, org, project, technology, or place | `entities` |
| User's name, date of birth, or core identity | `entities` + `facts` + `guardrails` (Identity) — all three |
| A permanent preference or behavioral rule | `facts` + `guardrails` (Interaction Preferences) — both |
| A one-off user preference | `facts` (user_preference) |
| Project-specific detail (path, username, config value) | `facts` (project_info) |
| URL, credential, file path, contact info | `facts` (reference) |
| A discrete event that happened | `episodes` |
| Something the user wants to do | `goals` |
| Long reference content (> 3 sentences) | `knowledge` |
| A multi-step solution that was executed and worked | `procedure` |
| "Always remember", "never forget", "from now on" | `guardrails` + `facts` — both |
| Code style or tool preference | `facts` + `guardrails` (Code Style) — both |

**Why cross-posting matters:**
- `Guardrails.md` is injected into **every** system prompt — things that must never be forgotten
- `Facts.md` is searchable — things that should be recalled on-demand
- `entities/` keeps named profiles current and deduplicated

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
- LLM extracts structured data across **all seven categories** including guardrails
- Each category is deduplicated before saving:
  - **Entities** — three-tier dedup (see Entity Deduplication section)
  - **Episodes** — matched by exact title; updated or appended
  - **Facts** — line-by-line scan of existing content; skipped if near-identical line exists
  - **Goals** — scans for `**title**` bullet pattern; marks complete in-place if status changes
  - **Procedure** — exact heading match first, then QMD similarity against procedure category (> 0.75 score); skipped if near-identical procedure exists
  - **Guardrails** — substring scan of existing rules; skipped if near-identical rule exists; routed to correct section
- A session log is saved to `sessions/<epoch>.md` with a summary and backlinks
- If any file exceeds 500 lines, it is auto-split into a subdirectory

### 4. Guardrails (`system_prompt`)
On every turn:
- Reads `Guardrails.md`
- Injects its contents at the top of the system prompt — highest priority, always active

---

## Entity Deduplication

Entity deduplication uses three tiers, each a fallback for the previous:

```
New entity extracted (e.g. "vismay", type: person)
      │
      ▼ Tier 0
[Exact match] — case-insensitive ## heading search
      │ not found
      ▼ Tier 1
[Fuzzy match] — token_sort_ratio + whole-word subset check
      │          "vismay" → "Vismay Zaveri" (subset match, score 90)
      │          "aivismayzaveri" → "Vismay Zaveri" (token ratio, score 89)
      │ not found above threshold (default: 82)
      ▼ Tier 2 (opt-in; enable in UI settings + run Execute to download model)
[GLinker semantic linking] — neural model resolves via entity descriptions
      │          "GH" → "GitHub" (abbreviation, context-based)
      │          "the company" → "Anthropic" (descriptive reference)
      │ not found above acceptance threshold (default: 0.75)
      ▼
[Create new entity]
```

### Tier 1: Fuzzy matching

Always active. Uses `rapidfuzz` if installed, falls back to Python's built-in `difflib`.

The scorer combines:
- **`token_sort_ratio`** — handles character-level overlap and word reordering (`aivismayzaveri` ↔ `Vismay Zaveri` = 89)
- **Whole-word subset check** — if all words in the query appear in the stored name (or vice versa), scores 90 regardless of ratio (`vismay` ↔ `Vismay Zaveri` = 90)

Configurable threshold (default 82). Lower = more aggressive merging (more false positives). Higher = more conservative (more duplicate entities).

### Tier 2: GLinker semantic linking

Uses the [GLinker](https://github.com/Knowledgator/GLinker) framework for neural entity linking. Catches cases where there is no string overlap between the mention and the stored entity name — resolved instead by matching against stored entity **descriptions**.

**When Tier 2 adds value over Tier 1:**
- Abbreviations: `GH` → `GitHub`, `MS` → `Microsoft`
- Descriptive references: `the framework` → `Agent Zero`
- Foreign-script or transliterated names: `aivismayzaveri` → `Vismay Zaveri` (GitHub username, matched via stored description "GitHub username aivismayzaveri")

**How it works:**
- The executor is built with `template="{label}: {description}"` — so L3 scores new mentions against the full stored entity description, not just the entity name
- The input is `"name (type)"` only — raw context is **not** passed, because passing context that mentions other entity names (e.g. "GitHub username") causes the linker to match those entities instead
- The GLinker executor runs with an internal threshold of 0.40 to surface all candidates; the config `entity_glinker_threshold` (default 0.75) is then applied as an acceptance filter on the returned confidence score

**Tested results at threshold 0.75:**
| Input | Resolved to | Confidence |
|---|---|---|
| `vismay (person)` | Vismay Zaveri | 0.893 |
| `aivismayzaveri (person)` | Vismay Zaveri | 0.839 |
| `agent zero (project)` | Agent Zero | 0.802 |
| `ssh (tech)` | SSH | 0.798 |
| `claude (tech)` | Claude | 0.871 |
| `randomxyz123 (misc)` | — *(rejected, conf=0.687)* | — |

**Disabled by default** — must be explicitly enabled. The model is downloaded only when you run **Execute** with it enabled, not at startup.

Config:
```yaml
entity_glinker_enabled: false    # set to true in plugin UI, then run Execute
entity_glinker_model: "knowledgator/gliner-linker-base-v1.0"  # ~230 MB
entity_glinker_threshold: 0.75   # acceptance filter; executor runs at 0.40 internally
entity_glinker_device: "cpu"     # or "cuda" if GPU available
```

Once enabled and the model is cached, it is loaded lazily on first extraction and reused for the session. If the `glinker` package is missing or the model fails to load, the system falls back to Tier 1 silently.

---

## Agent Tools

The agent can interact with memory manually using these tools:

| Tool | What it does |
|---|---|
| `memory_search` | Search memories with a query; returns scored results |
| `memory_save` | Save new information to a specific category (entities use full 3-tier dedup) |
| `memory_update` | Update an existing memory entry by heading |
| `memory_browse` | Read an entire category or section |
| `memory_import` | Import an external file (PDF, HTML, CSV, etc.) into the docs collection |
| `guardrails_update` | Add or modify behavioral rules in Guardrails.md |

### Memory categories

| Category value | File(s) | What it contains |
|---|---|---|
| `entities` | `entities/*.md` | Named people, orgs, projects, technologies, places |
| `facts` | `Facts.md` | User preferences, project info, URLs, one-off details |
| `guardrails` | `Guardrails.md` | Always-on identity and behavioral rules |
| `episodes` | `Episodes.md` | Past events and timeline entries |
| `goals` | `Goals.md` | Active and completed tasks |
| `knowledge` | `Knowledge.md` | Long-form reference content |
| `procedure` | `Procedure.md` | Step-by-step solutions that worked |
| `sessions` | `sessions/*.md` | Per-conversation summaries |
| `docs` | `docs/*` | Externally imported documents |

### Search pipeline

Searches go through three stages before results are returned:

```
Raw query from agent
      │
      ▼
[1. Query normalization] — utility LLM strips noise words
      │  "Vismay Zaveri birth date birthday personal info"
      │  → "date of birth Vismay Zaveri"
      ▼
[2. QMD hybrid search] — BM25 + semantic embeddings
      │  (expanded limit when category filter is used)
      ▼
[3. Post-processing] — temporal decay → MMR diversity filter
      │
      ▼  if category specified:
[4. Category filter] — keep only results matching the requested category
      │  if 0 results after filtering:
      ▼
[5. Fallback search] — retry with "{category} {query}" to bias QMD
      │
      ▼
Results returned to agent
```

**Two-pass category retrieval:** When a category filter is used, QMD is queried with a 3× expanded limit before filtering. If filtering still yields nothing, a second search runs with the category name prepended to the query. This prevents the original failure mode where relevant files ranked just outside the global top-N and were silently dropped.

**Category aliases** are supported — the tool accepts singular, plural, and common variations:
`entity` → `entities`, `task` / `tasks` → `goals`, `howto` → `procedure`, `rule` → `guardrails`, etc.

**Query normalization** (controlled by `memory_search_query_prep: true`) strips noise before sending to QMD:
- Raw: `"Vismay Zaveri birth date birthday personal info"` → poor results
- Normalized: `"date of birth Vismay Zaveri"` → 0.87 score

**Recommended search strategy:**
- Omit category when unsure — broadest coverage, uses the full file set
- Use category only when you know exactly where the answer lives
- For multi-topic questions, run separate searches per topic:
```
"What are my goals and what do I know about the agentzero project?"
  → search 1: query="active goals",   category="goals"
  → search 2: query="agentzero",      category="entities"
  → search 3: query="agentzero",      category="facts"
```
- If a category search returns 0 results, retry without the category filter before concluding the information is not stored

---

## Search Engine (QMD)

QMD (`@tobilu/qmd`) is a local Node.js search engine that combines:
- **BM25** — classic keyword/full-text ranking
- **Semantic embeddings** — meaning-based similarity

Results are further post-processed by:
- **Temporal decay** — older memories get a lower score (`score × e^(−λ × days_old)`, half-life configurable, default 30 days)
- **MMR (Maximal Marginal Relevance)** — reranks results to balance relevance with diversity, preventing near-identical snippets eating your token budget

The QMD engine runs as a local CLI (`node qmd.js`) called via subprocess. All calls degrade gracefully — if QMD fails, memory recall returns empty rather than crashing the agent.

---

## Concurrent Write Safety

All read-modify-write operations on memory files are protected by a **per-file threading lock**. This prevents data loss when background extraction, auto-recall, and tool calls fire concurrently in the same Agent Zero process.

```
Without locking:                    With locking:
Thread A reads Facts.md (200 lines) Thread A acquires lock on Facts.md
Thread B reads Facts.md (200 lines) Thread B waits...
Thread A writes 201 lines           Thread A writes 201 lines, releases lock
Thread B writes 201 lines           Thread B acquires lock, reads 201 lines
← Thread A's fact is lost           Thread B writes 202 lines ✓
```

Different files (e.g. Facts.md and people.md) can be written in parallel — only writes to the **same file** are serialized.

The lock pool is bounded to 200 entries to prevent unbounded memory growth. When the limit is reached, unlocked entries are evicted to make room.

---

## Key Configuration (`default_config.yaml`)

### Recall

| Setting | Default | Description |
|---|---|---|
| `memory_recall_enabled` | `true` | Enable automatic memory recall |
| `memory_recall_interval` | `3` | Recall every N agent iterations |
| `memory_recall_max_results` | `8` | Max memories injected per recall |
| `memory_recall_token_budget` | `3000` | Max tokens for recalled memories |
| `memory_recall_query_prep` | `false` | Use LLM to optimize auto-recall queries |
| `memory_recall_delayed` | `false` | Async mode — memories appear next iteration |

### Extraction

| Setting | Default | Description |
|---|---|---|
| `memory_extract_enabled` | `true` | Enable automatic extraction at conversation end |
| `memory_extract_min_chars` | `200` | Min user chars to trigger extraction |
| `memory_extract_min_tool_calls` | `2` | Min tool calls to trigger extraction |
| `memory_extract_categories` | all 7 | Categories to extract (includes `guardrails`) |

### Entity Deduplication

| Setting | Default | Description |
|---|---|---|
| `entity_dedup_enabled` | `true` | Enable entity deduplication |
| `entity_fuzzy_threshold` | `82` | Fuzzy match threshold 0–100 (lower = more merging) |
| `entity_glinker_enabled` | `false` | Enable GLinker semantic linking (Tier 2); set via UI then run Execute to download model |
| `entity_glinker_model` | `gliner-linker-base-v1.0` | GLinker model to use |
| `entity_glinker_threshold` | `0.75` | Acceptance filter on GLinker confidence score (executor runs at 0.40 internally) |
| `entity_glinker_device` | `cpu` | Torch device (`cpu` or `cuda`) |

### Search

| Setting | Default | Description |
|---|---|---|
| `memory_search_query_prep` | `true` | Normalize manual `memory_search` queries via LLM |
| `qmd_search_limit` | `10` | Raw QMD result limit before post-processing |
| `qmd_timeout_sec` | `10` | QMD subprocess timeout |

### Ranking & Diversity

| Setting | Default | Description |
|---|---|---|
| `memory_temporal_decay_enabled` | `true` | Recent memories rank higher |
| `memory_temporal_decay_halflife_days` | `30` | Half-life for temporal decay |
| `memory_mmr_enabled` | `true` | MMR diversity filter on results |
| `memory_mmr_lambda` | `0.7` | 1.0 = pure relevance, 0.0 = pure diversity |

### Storage

| Setting | Default | Description |
|---|---|---|
| `memory_dir` | `/a0/usr/memory` | Where memory files are stored |
| `memory_per_agent` | `false` | Give each sub-agent its own memory folder |
| `auto_split_threshold_lines` | `500` | Split large files into subdirectories at this size |
| `guardrails_enabled` | `true` | Inject Guardrails.md into every system prompt |
| `memory_precompact_enabled` | `true` | Warn agent before context compaction |
| `memory_precompact_threshold_chars` | `40000` | Context size that triggers compaction warning |

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
│   │   └── _10_qmd_memory_init.py            # Initialization on conversation start
│   ├── message_loop_prompts_after/
│   │   ├── _50_recall_memories.py            # Memory recall injection
│   │   ├── _80_precompact_check.py           # Warn agent before context compaction
│   │   └── _91_recall_wait.py                # Wait for async search to complete
│   ├── monologue_end/
│   │   └── _50_extract_memories.py           # Memory extraction at conversation end
│   └── system_prompt/
│       └── _20_guardrails_prompt.py          # Inject Guardrails.md into system prompt
│
├── tools/
│   ├── memory_search.py         # Hybrid search: query normalization + two-pass category retrieval
│   ├── memory_save.py
│   ├── memory_update.py
│   ├── memory_browse.py
│   ├── memory_import.py
│   └── guardrails_update.py
│
├── helpers/
│   ├── memory_files.py          # File I/O: atomic writes, per-file locks, dedup, split
│   ├── qmd_client.py            # QMD CLI wrapper (search, reindex, collection mgmt)
│   ├── session_log.py           # Session summary creation
│   └── entity_linker.py         # GLinker Tier-2 entity linking (opt-in via UI settings)
│
├── api/
│   ├── search.py                # POST /api/plugins/qmd_memory/search
│   ├── index.py                 # POST /api/plugins/qmd_memory/index
│   └── status.py                # POST /api/plugins/qmd_memory/status
│
├── prompts/
│   ├── extraction.system.md          # LLM extraction schema with routing guide
│   ├── extraction.message.md         # Template: passes conversation history to LLM
│   ├── search.query.sys.md           # LLM prompt for manual search query normalization
│   ├── recall.query.sys.md           # LLM prompt for auto-recall query optimization
│   ├── agent.system.memories.md      # Template for injecting recalled memories
│   ├── agent.system.guardrails.md    # Template for injecting guardrails
│   ├── agent.system.tool.qmd_memory.md  # Tool docs shown to the agent
│   ├── behaviour.merge.sys.md           # LLM prompt for guardrails merge
│   ├── behaviour.merge.msg.md           # Template: passes current rules + adjustments
│   └── ...                           # Other confirmation/response templates
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
5. Install optional Python dependencies (`rapidfuzz`, `pdfminer.six`, `pypdf`, `markdownify`) for full functionality

### GLinker (Tier-2 entity dedup)

GLinker is **disabled by default**. To enable it:

1. Open the plugin settings in the Agent Zero UI
2. Toggle **"Enable GLinker semantic linking (Tier 2)"** on
3. Save settings
4. Click **Execute** — this downloads the model (~230 MB from Hugging Face) and warms it

The model is cached locally after the first download. No internet required after that. CPU inference is supported; select `cuda` in settings if a compatible GPU is available.

If `glinker` is not installed, `execute.py` will install it automatically when GLinker is enabled.

---

## Known Limitations & Trade-offs

| Area | Behaviour | Note |
|---|---|---|
| Category search coverage | Two-pass retrieval (3× limit + fallback) reduces misses but cannot guarantee results if the memory genuinely doesn't exist or scores very low | If a category search still returns nothing, retry without the category filter |
| Fuzzy entity threshold | Default 82 — may merge entities with similar but distinct names (e.g. "Agent Zero" ↔ "agentzero") | Raise threshold to 88+ if false merges occur; extraction prompt instructs consistent naming |
| GLinker cold start | Model loads lazily on first extraction — takes 5–15 s to initialize (embedding pre-computation included) | Subsequent calls in the same session use the cached in-process executor; model files are cached on disk after first download |
| Procedure dedup | QMD similarity threshold 0.75 — may occasionally miss near-duplicate procedures with very different wording | Review Procedure.md periodically and remove duplicates manually |
| Cross-process locking | Per-file threading locks protect concurrent threads within one Agent Zero process; they do NOT protect against two separate processes writing the same file simultaneously | Only relevant if running multiple Agent Zero instances pointing at the same memory directory |
| Session log growth | `sessions/` accumulates one file per conversation indefinitely | No automatic cleanup; archive or delete old sessions manually as needed |
| Entity name caching | Entity names are cached in-memory after first scan; cache is invalidated on writes | If entity files are modified outside the plugin (e.g. manual edit), restart the agent or call `memory_save` to trigger cache invalidation |
