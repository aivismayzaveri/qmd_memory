"""
QMD Memory Plugin - QMD CLI Wrapper

All QMD subprocess interactions go through this module.
Provides graceful degradation: on any failure, logs a warning and returns empty/False.

Command mapping (from QMD docs):
  qmd collection add <path> --name <n>  — register a named collection
  qmd context add qmd://<name> "<desc>" — describe collection for LLM relevance (key QMD feature)
  qmd embed                             — generate semantic embeddings (needed for hybrid search)
  qmd update                            — reindex BM25/text index after file changes
  qmd query <q> --json -n <n>           — hybrid search + reranking (best quality for LLMs)
  qmd get <file> --full                 — fetch full document content by path or docid
  qmd multi-get "<glob>" --full         — fetch multiple documents by glob pattern
  qmd status                            — health check
"""

import json
import math
import subprocess
import threading
from pathlib import Path
from helpers.print_style import PrintStyle

PLUGIN_DIR = Path(__file__).parent.parent
_DEFAULT_QMD_ENGINE = PLUGIN_DIR / "qmd_engine"
_QMD_CLI_REL = Path("node_modules") / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"

# Debounce state for post-write reindex
_reindex_timer: threading.Timer | None = None
_reindex_lock = threading.Lock()

# Collection name for the memory directory — used in qmd:// URIs and context registration
MEMORY_COLLECTION_NAME = "sessions"
MEMORY_COLLECTION_CONTEXT = "Agent interaction summaries with structured epochs"


def _extract_age_days(result: dict) -> float | None:
    """Extract age in days from a search result. Returns None if unknown."""
    import re
    from datetime import datetime, timezone

    path = result.get("path", "") or result.get("file", "")

    # Session files are epoch-named: <epoch>.md (9-10 digit numeric stem)
    m = re.search(r'[/\\](\d{9,10})\.md$', path)
    if m:
        epoch = int(m.group(1))
        now_epoch = datetime.now(timezone.utc).timestamp()
        return max(0, (now_epoch - epoch) / 86400)

    return None


def apply_temporal_decay(results: list[dict], half_life_days: float = 30.0) -> list[dict]:
    """
    Apply exponential decay to result scores based on session age.
    score_decayed = score * e^(-lambda * days_old)
    Recent sessions rank higher. Unknown-age results are unchanged.
    """
    lambda_decay = math.log(2) / half_life_days
    decayed = []
    for r in results:
        r = dict(r)
        age = _extract_age_days(r)
        if age is not None and age > 0:
            r["score_raw"] = r.get("score", 0)
            r["score"] = r["score_raw"] * math.exp(-lambda_decay * age)
        decayed.append(r)
    return sorted(decayed, key=lambda x: x.get("score", 0), reverse=True)


def _text_similarity(a: dict, b: dict) -> float:
    """Jaccard similarity between snippet word sets."""
    words_a = set((a.get("snippet", "") + " " + a.get("title", "")).lower().split())
    words_b = set((b.get("snippet", "") + " " + b.get("title", "")).lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def apply_mmr(results: list[dict], lambda_mmr: float = 0.7) -> list[dict]:
    """
    Maximal Marginal Relevance: reorder results to balance relevance with diversity.
    lambda_mmr=1.0 = pure relevance, 0.0 = pure diversity.
    Prevents near-identical session snippets consuming the token budget.
    """
    if len(results) <= 2:
        return results

    selected = []
    candidates = list(results)

    while candidates:
        if not selected:
            best = max(candidates, key=lambda x: x.get("score", 0))
        else:
            best = None
            best_mmr = float("-inf")
            for c in candidates:
                rel = c.get("score", 0)
                max_sim = max(_text_similarity(c, s) for s in selected)
                mmr = lambda_mmr * rel - (1 - lambda_mmr) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best = c
        selected.append(best)
        candidates.remove(best)

    return selected


def _get_qmd_cli(config: dict) -> tuple[Path, Path]:
    """Return (qmd_engine_dir, qmd_cli_path)."""
    engine_dir_str = config.get("qmd_engine_dir", "")
    engine_dir = Path(engine_dir_str) if engine_dir_str else _DEFAULT_QMD_ENGINE
    cli = engine_dir / _QMD_CLI_REL
    return engine_dir, cli


def _run(args: list[str], cwd: Path, timeout: int = 10) -> subprocess.CompletedProcess | None:
    """Run a subprocess, return None on failure."""
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        PrintStyle.warning(f"[QMD Memory] Command timed out: {' '.join(str(a) for a in args[:4])}")
        return None
    except FileNotFoundError:
        PrintStyle.warning(f"[QMD Memory] Command not found: {args[0]}")
        return None
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Subprocess error: {e}")
        return None


def search(query: str, config: dict, limit: int = 10) -> list[dict]:
    """
    Search the QMD index using hybrid search + reranking (qmd query).
    This is the highest-quality retrieval mode — combines BM25 keyword matching
    with semantic embeddings and applies reranking for LLM-quality results.
    Returns list of {title, path, score, snippet}.
    Returns empty list on any error (graceful degradation).
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return []

    timeout = int(config.get("qmd_timeout_sec", 30))
    result = _run(
        ["node", str(cli), "query", query, "--json", "-n", str(limit)],
        cwd=engine_dir,
        timeout=timeout,
    )

    if result is None or result.returncode != 0:
        if result:
            PrintStyle.warning(f"[QMD Memory] Query failed: {result.stderr[:200]}")
        return []

    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []

        # Normalize: QMD may return 'file' (qmd://sessions/…), copy to 'path' for consumers
        for r in data:
            if "path" not in r and "file" in r:
                r["path"] = r["file"]

        # Apply temporal decay if enabled (recent sessions rank higher)
        if config.get("memory_temporal_decay_enabled", True):
            half_life = float(config.get("memory_temporal_decay_halflife_days", 30))
            data = apply_temporal_decay(data, half_life)

        # Apply MMR diversity filter if enabled (avoid duplicate snippets)
        if config.get("memory_mmr_enabled", True):
            lambda_mmr = float(config.get("memory_mmr_lambda", 0.7))
            data = apply_mmr(data, lambda_mmr)

        return data
    except json.JSONDecodeError:
        PrintStyle.warning("[QMD Memory] Failed to parse query results JSON")
        return []


def search_all(query: str, config: dict, min_score: float = 0.0) -> list[dict]:
    """
    Find ALL matching sessions above a score threshold.
    Uses: qmd query <q> --all --files --min-score <s> --collection sessions
    Returns compact results: list of {docid, score, filepath, context}.
    Use this for discovery before calling get_document() on specific sessions.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return []

    timeout = int(config.get("qmd_timeout_sec", 30))
    args = [
        "node", str(cli), "query", query,
        "--all", "--json", "--min-score", str(min_score),
        "--collection", MEMORY_COLLECTION_NAME,
    ]
    result = _run(args, cwd=engine_dir, timeout=timeout)

    if result is None or result.returncode != 0:
        if result:
            PrintStyle.warning(f"[QMD Memory] search_all failed: {result.stderr[:200]}")
        return []

    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []
        for r in data:
            if "path" not in r and "file" in r:
                r["path"] = r["file"]
        return data
    except json.JSONDecodeError:
        PrintStyle.warning("[QMD Memory] Failed to parse search_all results JSON")
        return []


def get_document(path: str, config: dict) -> str:
    """
    Fetch the full content of a session file by path, epoch, or docid (#abc123).
    Uses qmd get <path> --full for complete document retrieval.
    Returns empty string on failure.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return ""

    timeout = int(config.get("qmd_timeout_sec", 30))
    result = _run(
        ["node", str(cli), "get", path, "--full"],
        cwd=engine_dir,
        timeout=timeout,
    )
    if result is None or result.returncode != 0:
        return ""
    return result.stdout.strip()


def multi_get(pattern: str, config: dict) -> str:
    """
    Fetch multiple session documents by glob pattern.
    Uses qmd multi-get "<pattern>" --full.
    Example: multi_get("17747*.md", config) for all sessions starting with that epoch prefix.
    Returns concatenated content or empty string on failure.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return ""

    timeout = int(config.get("qmd_timeout_sec", 30))
    result = _run(
        ["node", str(cli), "multi-get", pattern, "--full"],
        cwd=engine_dir,
        timeout=timeout,
    )
    if result is None or result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_document_section(path: str, config: dict, max_lines: int = 0, from_line: int = 0) -> str:
    """
    Fetch a section of a document with line-range control.
    Uses: qmd get <path>[:line] --full [-l <max_lines>] [--from <from_line>]
    Useful for reading specific parts of long session files.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return ""

    timeout = int(config.get("qmd_timeout_sec", 30))
    args = ["node", str(cli), "get", path, "--full", "--line-numbers"]
    if max_lines > 0:
        args.extend(["-l", str(max_lines)])
    if from_line > 0:
        args.extend(["--from", str(from_line)])

    result = _run(args, cwd=engine_dir, timeout=timeout)
    if result is None or result.returncode != 0:
        return ""
    return result.stdout.strip()


def add_collection(path: str, config: dict, name: str = MEMORY_COLLECTION_NAME) -> bool:
    """
    Register a directory as a named QMD collection.
    The name is used in qmd:// URIs for context registration.
    Returns True on success.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return False

    result = _run(
        ["node", str(cli), "collection", "add", path, "--name", name],
        cwd=engine_dir,
        timeout=30,
    )
    if result is None:
        return False
    return result.returncode == 0


def add_context(collection_name: str, description: str, config: dict) -> bool:
    """
    Register a human-readable description for a QMD collection.
    Uses qmd context add qmd://<name> "<description>".
    This is QMD's key feature — the description is returned alongside search results
    to give LLMs better context for choosing relevant documents.
    Returns True on success.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return False

    collection_uri = f"qmd://{collection_name}"
    result = _run(
        ["node", str(cli), "context", "add", collection_uri, description],
        cwd=engine_dir,
        timeout=15,
    )
    if result is None:
        return False
    return result.returncode == 0


def embed(config: dict) -> bool:
    """
    Generate semantic embeddings for all indexed documents.
    Must be run after qmd update to enable vsearch and the semantic
    component of qmd query (hybrid search).
    Returns True on success.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return False

    result = _run(
        ["node", str(cli), "embed"],
        cwd=engine_dir,
        timeout=120,
    )
    if result is None:
        return False
    return result.returncode == 0


def get_status(config: dict) -> dict:
    """Get QMD status. Returns dict with 'ready' key."""
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return {"ready": False, "qmd_installed": False}

    result = _run(["node", str(cli), "status"], cwd=engine_dir, timeout=15)
    if result is None:
        return {"ready": False, "error": "timeout"}
    return {
        "ready": result.returncode == 0,
        "qmd_installed": True,
        "output": result.stdout.strip(),
        "error": result.stderr.strip() or None,
    }


def reindex_async(config: dict) -> None:
    """
    Trigger a background reindex after a session file is written.
    Debounced by qmd_reindex_delay_ms to avoid rapid-fire rebuilds.
    Runs both qmd update (BM25 text index) and qmd embed (semantic embeddings)
    so that qmd query (hybrid search) works correctly.
    """
    global _reindex_timer

    delay_ms = int(config.get("qmd_reindex_delay_ms", 500))
    delay_sec = delay_ms / 1000.0

    with _reindex_lock:
        if _reindex_timer is not None:
            _reindex_timer.cancel()
        _reindex_timer = threading.Timer(delay_sec, _do_reindex, args=[config])
        _reindex_timer.daemon = True
        _reindex_timer.start()


def _do_reindex(config: dict) -> None:
    """
    Run qmd update then qmd embed in background.
    update: rebuilds the BM25/text index from disk
    embed:  generates semantic embeddings for new/changed documents
    Both are needed for qmd query (hybrid search + reranking) to work.
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return
    try:
        # Step 1: rebuild BM25/text index — must complete before embedding
        r = subprocess.run(
            ["node", str(cli), "update"],
            cwd=str(engine_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            PrintStyle.warning(f"[QMD Memory] qmd update failed: {r.stderr[:200]}")
            return
        # Step 2: generate semantic embeddings from the updated index
        # Must run after update — embeddings are built from the BM25 index
        subprocess.run(
            ["node", str(cli), "embed"],
            cwd=str(engine_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Reindex failed: {e}")
