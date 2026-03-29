"""
QMD Memory Plugin - QMD CLI Wrapper

All QMD subprocess interactions go through this module.
Provides graceful degradation: on any failure, logs a warning and returns empty/False.
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

# Module-level debounce timer
_reindex_timer: threading.Timer | None = None
_reindex_lock = threading.Lock()


def _extract_age_days(result: dict) -> float | None:
    """Extract age in days from a search result. Returns None if unknown."""
    import re
    from datetime import datetime, timezone

    path = result.get("path", "") or result.get("file", "")
    snippet = result.get("snippet", "")

    # Try session epoch from filename: sessions/1774702399.md
    m = re.search(r'/sessions/(\d{9,10})\.md', path)
    if m:
        epoch = int(m.group(1))
        now_epoch = datetime.now(timezone.utc).timestamp()
        return max(0, (now_epoch - epoch) / 86400)

    # Try Updated: YYYY-MM-DD in snippet
    m = re.search(r'\*\*Updated:\*\*\s*(\d{4}-\d{2}-\d{2})', snippet)
    if m:
        try:
            updated = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - updated).days)
        except Exception:
            pass

    return None


def apply_temporal_decay(results: list[dict], half_life_days: float = 30.0) -> list[dict]:
    """
    Apply exponential decay to result scores based on age.
    score_decayed = score * e^(-lambda * days_old), lambda = ln(2) / half_life_days
    Recent memories rank higher. Unknown-age results are unchanged.
    """
    lambda_decay = math.log(2) / half_life_days
    decayed = []
    for r in results:
        r = dict(r)
        age = _extract_age_days(r)
        if age is not None and age > 0:
            r["score"] = r.get("score", 0) * math.exp(-lambda_decay * age)
            r["score_raw"] = r.get("score", 0)
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
    Prevents 5 near-identical snippets consuming the token budget.
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
    if engine_dir_str:
        engine_dir = Path(engine_dir_str)
    else:
        engine_dir = _DEFAULT_QMD_ENGINE
    cli = engine_dir / _QMD_CLI_REL
    return engine_dir, cli


def _run(args: list[str], cwd: Path, timeout: int = 10) -> subprocess.CompletedProcess | None:
    """Run a subprocess, return None on failure."""
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        PrintStyle.warning(f"[QMD Memory] Command timed out: {' '.join(args[:3])}")
        return None
    except FileNotFoundError:
        PrintStyle.warning(f"[QMD Memory] Command not found: {args[0]}")
        return None
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Subprocess error: {e}")
        return None


def search(query: str, config: dict, limit: int = 10) -> list[dict]:
    """
    Search QMD index. Returns list of {title, path, score, snippet}.
    Returns empty list on any error (graceful degradation).
    """
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return []

    timeout = int(config.get("qmd_timeout_sec", 10))
    result = _run(
        ["node", str(cli), "search", query, "--json", "-n", str(limit)],
        cwd=engine_dir,
        timeout=timeout,
    )

    if result is None or result.returncode != 0:
        if result:
            PrintStyle.warning(f"[QMD Memory] Search failed: {result.stderr[:200]}")
        return []

    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []

        # Normalize: QMD returns 'file' (qmd://memory/…), copy to 'path' for consumers
        for r in data:
            if "path" not in r and "file" in r:
                r["path"] = r["file"]

        # Apply temporal decay if enabled
        if config.get("memory_temporal_decay_enabled", True):
            half_life = float(config.get("memory_temporal_decay_halflife_days", 30))
            data = apply_temporal_decay(data, half_life)

        # Apply MMR diversity filter if enabled
        if config.get("memory_mmr_enabled", True):
            lambda_mmr = float(config.get("memory_mmr_lambda", 0.7))
            data = apply_mmr(data, lambda_mmr)

        return data
    except json.JSONDecodeError:
        PrintStyle.warning("[QMD Memory] Failed to parse search results JSON")
        return []


def add_collection(path: str, config: dict) -> bool:
    """Register a directory as a QMD collection. Returns True on success."""
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return False

    result = _run(
        ["node", str(cli), "collection", "add", path],
        cwd=engine_dir,
        timeout=30,
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
    Trigger a background QMD reindex, debounced by qmd_reindex_delay_ms.
    Safe to call rapidly — only one reindex fires after the quiet window.
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
    """Actually run qmd update in a detached subprocess."""
    engine_dir, cli = _get_qmd_cli(config)
    if not cli.exists():
        return
    try:
        subprocess.Popen(
            ["node", str(cli), "update"],
            cwd=str(engine_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Reindex failed: {e}")
