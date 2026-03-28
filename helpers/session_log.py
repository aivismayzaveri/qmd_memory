"""
QMD Memory Plugin - Session Log Manager

Creates LLM-summarized session log files in sessions/<epoch>.md.
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
    Checks user-authored content length (not total history which includes the AI's long responses).
    Threshold: (user_chars >= min_chars) OR (tool_calls >= min_tool_calls)
    Falls back to total history length if user_chars not provided.
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
    """Count characters in user-role messages only, to avoid counting AI responses."""
    try:
        total = 0
        for msg in history:
            # Agent Zero history messages have a role attribute
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role in ("user", "human"):
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else str(msg))
                total += len(str(content))
        return total
    except Exception:
        return 0


async def create_session_log(
    agent,
    history_text: str,
    extraction: dict,
    memory_dir: str,
    config: dict,
) -> Optional[str]:
    """
    Create a session log file for this conversation.
    Returns the epoch string used as filename, or None if skipped.
    """
    epoch = str(int(time.time()))
    sessions_dir = Path(memory_dir) / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    log_path = sessions_dir / f"{epoch}.md"

    now = datetime.now(timezone.utc).isoformat()
    summary = extraction.get("session_summary", "No summary available.")

    # Build Extracted To section
    extracted_lines = []
    if extraction.get("entities"):
        names = [e.get("name", "?") for e in extraction["entities"]]
        extracted_lines.append(f"- entities: {', '.join(names)}")
    if extraction.get("episodes"):
        titles = [e.get("title", "?") for e in extraction["episodes"]]
        extracted_lines.append(f"- Episodes.md: {', '.join(titles)}")
    if extraction.get("facts"):
        extracted_lines.append(f"- Facts.md: {len(extraction['facts'])} fact(s)")
    if extraction.get("procedure"):
        titles = [p.get("title", "?") for p in extraction["procedure"]]
        extracted_lines.append(f"- Procedure.md: {', '.join(titles)}")
    if extraction.get("goals"):
        titles = [g.get("title", "?") for g in extraction["goals"]]
        extracted_lines.append(f"- Goals.md: {', '.join(titles)}")

    extracted_section = "\n".join(extracted_lines) if extracted_lines else "- (nothing extracted)"

    # Collect entity names and tags
    entity_names = [e.get("name", "") for e in extraction.get("entities", [])]
    tags = list({e.get("type", "") for e in extraction.get("entities", []) if e.get("type")})

    content = f"""---
schema_version: 1
type: session
epoch: {epoch}
date: "{now}"
agent: agent_0
summary: "{summary[:200].replace('"', "'")}"
entities: {entity_names}
tags: {tags}
---

# Session {epoch}

## Summary
{summary}

## Extracted To
{extracted_section}
"""

    try:
        from usr.plugins.qmd_memory.helpers.memory_files import _atomic_write
        _atomic_write(log_path, content)
    except Exception as e:
        PrintStyle.warning(f"[QMD Memory] Failed to write session log: {e}")
        return None

    return epoch
