"""
QMD Memory Plugin - Markdown Category File Manager

Handles all read/write/append/update operations on memory category files.
Uses atomic writes (write-to-temp → rename) to prevent corruption.
"""

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Map category names to their file paths (relative to memory_dir)
CATEGORY_FILES = {
    "episodes": "Episodes.md",
    "facts": "Facts.md",
    "knowledge": "Knowledge.md",
    "procedure": "Procedure.md",
    "goals": "Goals.md",
    "guardrails": "Guardrails.md",
    "docs": "docs",
}

ENTITY_SUBTYPES = {
    "person": "people",
    "people": "people",
    "project": "projects",
    "projects": "projects",
    "technology": "technologies",
    "technologies": "technologies",
    "organization": "organizations",
    "org": "organizations",
    "organizations": "organizations",
    "place": "places",
    "location": "places",
    "city": "places",
    "country": "places",
    "places": "places",
    "other": "other",
    "concept": "other",
    "service": "other",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a temp file then rename atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _update_frontmatter_timestamp(content: str) -> str:
    """Update the last_updated field in YAML frontmatter."""
    now = datetime.now(timezone.utc).isoformat()
    if content.startswith("---"):
        # Replace existing last_updated
        updated = re.sub(
            r'^last_updated:.*$',
            f'last_updated: "{now}"',
            content,
            flags=re.MULTILINE,
        )
        if updated == content:
            # Field not present — insert after first field
            updated = re.sub(r'^(---\n)', rf'\1last_updated: "{now}"\n', content, count=1)
        return updated
    return content


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].lstrip("\n")
    return content


def ensure_memory_structure(memory_dir: str) -> None:
    """Create full memory directory structure if it doesn't exist."""
    base = Path(memory_dir)
    base.mkdir(parents=True, exist_ok=True)
    (base / "sessions").mkdir(exist_ok=True)
    (base / "entities").mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    # Entity sub-files
    entity_subtypes = ["people", "projects", "technologies", "organizations", "places", "other"]
    for subtype in entity_subtypes:
        f = base / "entities" / f"{subtype}.md"
        if not f.exists():
            _atomic_write(f, f"""---
schema_version: 1
type: entities
subtype: {subtype}
last_updated: "{now}"
---

# {subtype.capitalize()}
""")

    # Entity index
    idx = base / "entities" / "_index.md"
    if not idx.exists():
        _atomic_write(idx, f"""---
schema_version: 1
type: entities_index
last_updated: "{now}"
---

# Entity Index

| Name | Type | File | Last Updated |
|------|------|------|--------------|
""")

    # Docs directory for imported documents
    docs_dir = base / "docs"
    docs_dir.mkdir(exist_ok=True)
    docs_idx = docs_dir / "_index.md"
    if not docs_idx.exists():
        _atomic_write(docs_idx, f"""---
schema_version: 1
type: docs_index
last_updated: "{now}"
---

# Imported Documents

| Title | File | Source | Imported |
|-------|------|--------|----------|
""")

    # Top-level category files
    category_defs = {
        "Episodes.md": ("episodes", "# Episodes\n"),
        "Facts.md": ("facts", "# Facts\n\n## User Preferences\n\n## Project Information\n\n## References & Links\n"),
        "Knowledge.md": ("knowledge", "# Knowledge\n"),
        "Procedure.md": ("procedure", "# Procedures\n"),
        "Goals.md": ("goals", "# Goals\n\n## Active\n\n## Completed\n"),
        "Guardrails.md": ("guardrails", "# Guardrails\n\n## Security\n\n## Interaction Preferences\n\n## Code Style\n"),
    }
    for filename, (cat_type, body) in category_defs.items():
        f = base / filename
        if not f.exists():
            _atomic_write(f, f"""---
schema_version: 1
type: {cat_type}
last_updated: "{now}"
---

{body}""")


def _category_path(memory_dir: str, category: str) -> Path:
    """Get the path to a category file (or dir for entities)."""
    base = Path(memory_dir)
    if category == "entities":
        return base / "entities"
    filename = CATEGORY_FILES.get(category)
    if filename:
        return base / filename
    raise ValueError(f"Unknown category: {category}")


def read_category(memory_dir: str, category: str) -> str:
    """Read full content of a category. For entities, concatenates all sub-files."""
    if category == "entities":
        entities_dir = Path(memory_dir) / "entities"
        parts = []
        for subfile in sorted(entities_dir.glob("*.md")):
            if subfile.name != "_index.md":
                parts.append(_read_file(subfile))
        return "\n\n".join(parts)
    path = _category_path(memory_dir, category)
    # Handle split categories (directory)
    if path.is_dir():
        parts = []
        for subfile in sorted(path.glob("*.md")):
            if subfile.name != "_index.md":
                parts.append(_read_file(subfile))
        return "\n\n".join(parts)
    return _read_file(path)


def read_category_raw(memory_dir: str, category: str, section: str = "") -> str:
    """
    Read a category file or a specific section within it.
    For entities, section = subtype name (e.g. 'people').
    """
    if category == "entities":
        if section:
            subtype_file = ENTITY_SUBTYPES.get(section.lower(), section)
            path = Path(memory_dir) / "entities" / f"{subtype_file}.md"
            return _read_file(path)
        else:
            return _read_file(Path(memory_dir) / "entities" / "_index.md")

    content = read_category(memory_dir, category)
    if not section:
        return content

    # Find ## Section heading
    pattern = rf'^## {re.escape(section)}.*?(?=^## |\Z)'
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(0).strip()
    return content  # return full if section not found


def append_to_category(memory_dir: str, category: str, content: str, epoch: str = "") -> None:
    """Append a new entry to a category file."""
    if category == "entities":
        raise ValueError("Use append_entity() for entity entries")

    path = _category_path(memory_dir, category)
    if path.is_dir():
        # Already split — append to the matching section's sub-file or default
        _append_to_split_dir(path, content, epoch)
        return

    existing = _read_file(path)
    # Add Updated timestamp if not present
    if epoch and "Updated:" not in content:
        content = content.rstrip() + f"\n- **Updated:** {_now_iso()}"
    if epoch and "Ref:" not in content:
        content = content.rstrip() + f"\n- _Ref: [session](sessions/{epoch}.md)_"

    new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    new_content = _update_frontmatter_timestamp(new_content)
    _atomic_write(path, new_content)


def append_to_section(memory_dir: str, category: str, section_heading: str, line: str) -> None:
    """
    Insert a line of content INSIDE an existing ## section heading.
    If the section doesn't exist, create it at the end.
    This prevents duplicate ## headings when appending facts/goals.
    """
    if category == "entities":
        raise ValueError("Use append_entity() for entity entries")

    path = _category_path(memory_dir, category)
    if path.is_dir():
        _append_to_split_dir(path, line, "")
        return

    content = _read_file(path)
    heading_pattern = re.compile(
        rf'^(## {re.escape(section_heading)}\s*\n)(.*?)(?=^## |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = heading_pattern.search(content)
    if match:
        # Insert the new line at the end of the section body
        section_body = match.group(2).rstrip()
        replacement = match.group(1) + (section_body + "\n" if section_body else "") + line.strip() + "\n\n"
        new_content = content[:match.start()] + replacement + content[match.end():]
    else:
        # Section doesn't exist — append heading + content
        new_content = content.rstrip() + f"\n\n## {section_heading}\n{line.strip()}\n"

    new_content = _update_frontmatter_timestamp(new_content)
    _atomic_write(path, new_content)


def _append_to_split_dir(dir_path: Path, content: str, epoch: str) -> None:
    """Append to the last sub-file in a split directory."""
    sub_files = sorted([f for f in dir_path.glob("*.md") if f.name != "_index.md"])
    target = sub_files[-1] if sub_files else dir_path / "part1.md"
    existing = _read_file(target)
    new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    new_content = _update_frontmatter_timestamp(new_content)
    _atomic_write(target, new_content)


def append_entity(memory_dir: str, entity: dict, epoch: str = "") -> None:
    """
    Append a new entity to the correct sub-file.
    entity: {"name": str, "type": str, "context": str}
    Also updates _index.md.
    """
    entity_type = entity.get("type", "other").lower()
    subtype = ENTITY_SUBTYPES.get(entity_type, "other")
    subfile = Path(memory_dir) / "entities" / f"{subtype}.md"
    name = entity.get("name", "Unknown")
    context = entity.get("context", "")

    entry = f"""
## {name}
- **Type:** {entity_type}
- **Context:** {context}
- **Updated:** {_now_iso()}
- **Sessions:** [{epoch}](../sessions/{epoch}.md)
"""
    existing = _read_file(subfile)
    new_content = existing.rstrip() + "\n" + entry.strip() + "\n"
    new_content = _update_frontmatter_timestamp(new_content)
    _atomic_write(subfile, new_content)

    # Update index
    _update_entity_index(memory_dir, name, entity_type, subtype)


def _update_entity_index(memory_dir: str, name: str, entity_type: str, subtype: str) -> None:
    """Add or update entity in _index.md."""
    index_path = Path(memory_dir) / "entities" / "_index.md"
    content = _read_file(index_path)
    today = _now_iso()
    new_row = f"| {name} | {entity_type} | {subtype}.md | {today} |"

    # Check if entity already in index
    if f"| {name} |" in content:
        # Update existing row
        content = re.sub(
            rf'\| {re.escape(name)} \|.*',
            new_row,
            content,
        )
    else:
        content = content.rstrip() + "\n" + new_row + "\n"

    content = _update_frontmatter_timestamp(content)
    _atomic_write(index_path, content)


def find_entity(memory_dir: str, name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Search for an entity by name across all sub-files.
    Returns (subfile_path, entry_content) or (None, None) if not found.
    """
    entities_dir = Path(memory_dir) / "entities"
    for subfile in entities_dir.glob("*.md"):
        if subfile.name == "_index.md":
            continue
        content = _read_file(subfile)
        # Look for ## EntityName heading (case-insensitive)
        pattern = rf'^## {re.escape(name)}\s*$'
        if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            # Extract the entry block
            match = re.search(
                rf'^## {re.escape(name)}.*?(?=^## |\Z)',
                content,
                re.MULTILINE | re.DOTALL | re.IGNORECASE,
            )
            entry = match.group(0).strip() if match else ""
            return str(subfile), entry
    return None, None


def update_entity(memory_dir: str, name: str, new_context: str, new_epoch: str = "") -> bool:
    """
    Merge new context into an existing entity.
    Returns True if found and updated.
    """
    subfile_path, existing_entry = find_entity(memory_dir, name)
    if not subfile_path:
        return False

    subfile = Path(subfile_path)
    content = _read_file(subfile)

    # Update the entry block
    today = _now_iso()
    updated_entry = re.sub(
        r'\*\*Context:\*\*.*',
        f'**Context:** {new_context}',
        existing_entry,
    )
    updated_entry = re.sub(
        r'\*\*Updated:\*\*.*',
        f'**Updated:** {today}',
        updated_entry,
    )
    if new_epoch:
        # Add session backlink if not already there
        if f"sessions/{new_epoch}.md" not in updated_entry:
            updated_entry = re.sub(
                r'(\*\*Sessions:\*\*.*)',
                rf'\1, [{new_epoch}](../sessions/{new_epoch}.md)',
                updated_entry,
            )
            if "**Sessions:**" not in updated_entry:
                updated_entry += f"\n- **Sessions:** [{new_epoch}](../sessions/{new_epoch}.md)"

    # Replace in file
    new_content = re.sub(
        rf'^## {re.escape(name)}.*?(?=^## |\Z)',
        updated_entry.strip() + "\n\n",
        content,
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    new_content = _update_frontmatter_timestamp(new_content)
    _atomic_write(subfile, new_content)
    return True


def find_entry(memory_dir: str, category: str, heading: str) -> Optional[str]:
    """Find an entry by ## heading in a category file. Returns entry text or None."""
    content = read_category(memory_dir, category)
    pattern = rf'^## {re.escape(heading)}.*?(?=^## |\Z)'
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(0).strip() if match else None


def update_entry(memory_dir: str, category: str, heading: str, new_content_body: str) -> bool:
    """
    Replace the content of an entry identified by ## heading.
    Preserves session backlinks. Returns True if found.
    """
    path = _category_path(memory_dir, category)
    if path.is_dir():
        # Search across sub-files
        for subfile in path.glob("*.md"):
            if subfile.name == "_index.md":
                continue
            content = _read_file(subfile)
            if re.search(rf'^## {re.escape(heading)}\s*$', content, re.MULTILINE | re.IGNORECASE):
                new_file_content = _replace_entry_in_content(content, heading, new_content_body)
                new_file_content = _update_frontmatter_timestamp(new_file_content)
                _atomic_write(subfile, new_file_content)
                return True
        return False

    content = _read_file(path)
    if not re.search(rf'^## {re.escape(heading)}\s*$', content, re.MULTILINE | re.IGNORECASE):
        return False

    new_file_content = _replace_entry_in_content(content, heading, new_content_body)
    new_file_content = _update_frontmatter_timestamp(new_file_content)
    _atomic_write(path, new_file_content)
    return True


def _replace_entry_in_content(content: str, heading: str, new_body: str) -> str:
    """Replace the ## heading block in content with new_body."""
    today = _now_iso()
    # Ensure Updated timestamp
    if "Updated:" not in new_body:
        new_body = new_body.rstrip() + f"\n- **Updated:** {today}"

    replacement = f"## {heading}\n{new_body.strip()}\n\n"

    return re.sub(
        rf'^## {re.escape(heading)}.*?(?=^## |\Z)',
        replacement,
        content,
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
        count=1,
    )


def check_and_split(memory_dir: str, category: str, threshold: int = 500) -> bool:
    """
    If a category file exceeds threshold lines, split it into a directory.
    Returns True if split occurred.
    """
    path = _category_path(memory_dir, category)
    if not path.exists() or path.is_dir():
        return False

    content = _read_file(path)
    lines = content.splitlines()
    if len(lines) <= threshold:
        return False

    # Split by ## Section headings
    split_dir = path.parent / path.stem.lower()
    split_dir.mkdir(exist_ok=True)

    # Parse sections
    sections: list[tuple[str, str]] = []
    current_heading = "general"
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines)))
            current_heading = line[3:].strip().lower().replace(" ", "_")
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines)))

    now = datetime.now(timezone.utc).isoformat()
    # Write each section to its own file
    for heading, body in sections:
        section_file = split_dir / f"{heading}.md"
        section_content = f"""---
schema_version: 1
type: {category}
subtype: {heading}
last_updated: "{now}"
---

{body}
"""
        _atomic_write(section_file, section_content)

    # Write index
    index_content = f"""---
schema_version: 1
type: {category}_index
last_updated: "{now}"
---

# {category.capitalize()} Index

"""
    for heading, _ in sections:
        index_content += f"- [{heading}]({heading}.md)\n"
    _atomic_write(split_dir / "_index.md", index_content)

    # Remove old single file, rename dir to match
    # Actually, keep old file as backup with .bak extension
    path.rename(str(path) + ".bak")

    return True


def get_guardrails_text(memory_dir: str) -> str:
    """Read Guardrails.md and return body (frontmatter stripped)."""
    path = Path(memory_dir) / "Guardrails.md"
    content = _read_file(path)
    return _strip_frontmatter(content).strip()


def write_guardrails(memory_dir: str, content: str) -> None:
    """Write new content to Guardrails.md, preserving frontmatter."""
    path = Path(memory_dir) / "Guardrails.md"
    existing = _read_file(path)

    # Extract frontmatter
    if existing.startswith("---"):
        end = existing.find("---", 3)
        frontmatter = existing[: end + 3]
    else:
        now = datetime.now(timezone.utc).isoformat()
        frontmatter = f'---\nschema_version: 1\ntype: guardrails\nlast_updated: "{now}"\n---'

    new_file = _update_frontmatter_timestamp(frontmatter + "\n\n" + content.strip() + "\n")
    _atomic_write(path, new_file)


def save_doc(memory_dir: str, title: str, content: str, source: str = "", tags: list = None) -> str:
    """
    Save an imported document to docs/<date>_<slug>.md.
    Returns the filename of the saved doc.
    Updates docs/_index.md.
    """
    import re

    now_iso = datetime.now(timezone.utc).isoformat()
    today = _now_iso()

    # Sanitize title to filename slug
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]
    filename = f"{today}_{slug}.md"

    docs_dir = Path(memory_dir) / "docs"
    docs_dir.mkdir(exist_ok=True)
    doc_path = docs_dir / filename

    tags_str = ", ".join(tags) if tags else ""
    frontmatter = f"""---
schema_version: 1
type: imported_doc
title: "{title.replace('"', "'")}"
source: "{source}"
imported: "{now_iso}"
tags: [{tags_str}]
---

"""
    _atomic_write(doc_path, frontmatter + content.strip() + "\n")

    # Update _index.md
    idx_path = docs_dir / "_index.md"
    idx_content = _read_file(idx_path)
    new_row = f"| {title} | [{filename}]({filename}) | {source[:60] if source else '-'} | {today} |"
    idx_content = idx_content.rstrip() + "\n" + new_row + "\n"
    idx_content = _update_frontmatter_timestamp(idx_content)
    _atomic_write(idx_path, idx_content)

    return filename
