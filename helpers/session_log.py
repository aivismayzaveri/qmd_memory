"""
QMD Memory Plugin - Session Log Manager

Creates LLM-summarized session log files directly in memory_dir/<epoch>.md.
Skips trivial conversations that don't meet minimum thresholds.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from helpers.print_style import PrintStyle


def should_create_log(history_text: str, tool_call_count: int, config: dict, user_chars: int = 0) -> bool:
    """
    Returns True if this conversation meets the minimum threshold for a session log.
    Threshold: (user_chars >= min_chars) OR (tool_calls >= min_tool_calls)
    """
    min_chars = int(config.get("memory_extract_min_chars", 200))
    min_tools = int(config.get("memory_extract_min_tool_calls", 2))
    check_chars = user_chars if user_chars > 0 else len(history_text)
    return check_chars >= min_chars or tool_call_count >= min_tools


def count_tool_calls(history) -> int:
    """Count the number of tool calls in the agent history."""
    try:
        count = 0
        for msg in history:
            msg_text = str(msg)
            if "tool_name" in msg_text or '"tool"' in msg_text.lower():
                count += 1
        return count
    except Exception:
        return 0


def count_user_chars(history) -> int:
    """Count characters in user-role messages only."""
    try:
        total = 0
        for msg in history:
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role in ("user", "human"):
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else str(msg))
                total += len(str(content))
        return total
    except Exception:
        return 0


async def create_session_log(
    agent,
    summary: str,
    memory_dir: str,
    config: dict,
) -> Optional[str]:
    """
    Create a session log file at memory_dir/<epoch>.md.
    Returns the epoch string used as filename, or None if failed.
    """
    epoch = str(int(time.time()))
    log_path = Path(memory_dir) / f"{epoch}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    content = f"""---
schema_version: 1
type: session
epoch: {epoch}
date: "{now}"
agent: agent_0
summary: "{summary[:200].replace('"', "'")}"
---

# Session {epoch}

## Summary
{summary}
"""

    try:
        from usr.plugins.qmd_memory.helpers.memory_files import _atomic_write
        _atomic_write(log_path, content)
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Failed to write session log: {e}")
        return None

    return epoch
