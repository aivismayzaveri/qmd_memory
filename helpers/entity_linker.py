"""
QMD Memory Plugin — Optional GLinker Entity Linker

Provides semantic entity deduplication using the GLinker framework.
This is Tier 2 on top of fuzzy string matching (Tier 1).

Tier 1 (fuzzy) catches: "vismay" → "Vismay Zaveri", case variants, partial names.
Tier 2 (GLinker) catches: "aivismayzaveri" → "Vismay Zaveri" (no string overlap,
    resolved by matching entity names against stored entity descriptions via neural
    linker model using template="{label}: {description}").

Enable via config:
    entity_glinker_enabled: true
    entity_glinker_model: "knowledgator/gliner-linker-base-v1.0"   # ~230MB
    entity_glinker_threshold: 0.75   # Raised from 0.40 — reduces false positives
    entity_glinker_device: "cpu"

GLinker is NOT a default dependency. Install with:
    pip install glinker
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

from helpers.print_style import PrintStyle


class GLinkerEntityLinker:
    """
    Lazy-initialised GLinker executor for entity deduplication.

    Converts the memory entity files into a GLinker knowledge base and uses
    the linker model to resolve new entity mentions to canonical stored names.

    Thread-safe: initialization is protected by a lock so only one thread
    loads the model even if multiple extractions fire in parallel.
    """

    def __init__(self, memory_dir: str, config: dict):
        self.memory_dir = memory_dir
        self.config = config
        self._executor = None
        self._init_lock = threading.Lock()
        self._failed = False          # Don't retry after a hard failure
        self._loaded_entity_count = 0

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def find_canonical(
        self,
        name: str,
        context: str = "",
        entity_type: str = "",
    ) -> tuple[Optional[str], float]:
        """
        Resolve a new entity mention to a canonical existing entity.

        Parameters
        ----------
        name        The raw entity name from extraction (e.g. "aivismayzaveri")
        context     One-sentence context from extraction (e.g. "User's GitHub username")
        entity_type Entity type string (e.g. "person", "project")

        Returns
        -------
        (canonical_name, confidence)  where canonical_name matches a ## heading
        in the entity files, or (None, 0.0) if no confident match found.
        """
        if self._failed:
            return None, 0.0

        executor = self._get_executor()
        if executor is None:
            return None, 0.0

        threshold = float(self.config.get("entity_glinker_threshold", 0.40))

        # Build input text: "name (type)"
        # We intentionally omit the raw context string here — passing context that
        # mentions other entity names (e.g. "GitHub username") confuses the linker
        # into matching those entities instead. The description template already
        # provides rich disambiguation via stored entity descriptions.
        text = f"{name} ({entity_type})" if entity_type else name

        try:
            result = executor.execute({"texts": [text]})
            l0 = result.get("l0_result")
            if not l0 or not l0.entities or not l0.entities[0]:
                return None, 0.0

            top = l0.entities[0][0]
            if top.is_linked:
                conf = float(getattr(top.linked_entity, "confidence",
                                     getattr(top.linked_entity, "score", 0.0)))
                if conf >= threshold:
                    return top.linked_entity.entity_id, conf

        except Exception as e:
            PrintStyle.warning(f"[GLinker] Linking failed for '{name}': {e}")

        return None, 0.0

    def reload(self) -> None:
        """Force-reload the knowledge base from current entity files."""
        with self._init_lock:
            self._executor = None
            self._failed = False

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _get_executor(self):
        """Return (or lazily initialise) the GLinker executor."""
        if self._executor is not None:
            return self._executor

        with self._init_lock:
            # Double-checked locking
            if self._executor is not None:
                return self._executor
            if self._failed:
                return None

            try:
                self._executor = self._build_executor()
            except ImportError:
                PrintStyle.warning(
                    "[GLinker] glinker package not installed. "
                    "Install with: pip install glinker\n"
                    "Falling back to fuzzy matching only."
                )
                self._failed = True
            except Exception as e:
                PrintStyle.warning(f"[GLinker] Initialisation failed: {e}")
                self._failed = True

        return self._executor

    def _build_executor(self):
        """Build and return a GLinker ProcessorFactory executor."""
        from glinker import ProcessorFactory  # type: ignore

        entities = self._load_entities()
        if not entities:
            PrintStyle.warning("[GLinker] No entities found in memory files — skipping init.")
            return None

        model = self.config.get(
            "entity_glinker_model",
            "knowledgator/gliner-linker-base-v1.0",
        )
        device = self.config.get("entity_glinker_device", "cpu")

        PrintStyle.print(
            f"[GLinker] Loading entity linker model '{model}' "
            f"({len(entities)} entities, device={device})..."
        )

        # Keep the executor's internal threshold low (0.40) so all candidates
        # reach the l0_result. Our acceptance filter (entity_glinker_threshold,
        # default 0.75) is applied in find_canonical(). Setting executor threshold
        # to 0.75 suppresses results before they surface, breaking recall.
        executor = ProcessorFactory.create_simple(
            model_name=model,
            device=device,
            threshold=0.40,
            template="{label}: {description}",
            entities=entities,
            precompute_embeddings=True,
            verbose=False,
        )

        self._loaded_entity_count = len(entities)
        PrintStyle.print(f"[GLinker] Ready with {len(entities)} entities.")
        return executor

    def _load_entities(self) -> list[dict]:
        """
        Parse all entity files and return GLinker-format records:
            {"entity_id": "Vismay Zaveri", "label": "Vismay Zaveri", "description": "..."}

        entity_id = the ## heading name (canonical key used for dedup).
        description = the **Context:** line (provides disambiguation signal).
        """
        entities = []
        entities_dir = Path(self.memory_dir) / "entities"

        for subfile in sorted(entities_dir.glob("*.md")):
            if subfile.name == "_index.md":
                continue
            content = subfile.read_text(encoding="utf-8")

            for block_match in re.finditer(
                r'^## (.+?)$(.*?)(?=^## |\Z)',
                content,
                re.MULTILINE | re.DOTALL,
            ):
                name = block_match.group(1).strip()
                body = block_match.group(2)

                # Extract **Context:** value
                ctx = re.search(r'\*\*Context:\*\*\s*(.+)', body)
                description = ctx.group(1).strip() if ctx else ""

                # Extract **Type:** value and fold into description for richer signal
                typ = re.search(r'\*\*Type:\*\*\s*(.+)', body)
                if typ:
                    description = f"{typ.group(1).strip()} — {description}" if description else typ.group(1).strip()

                entities.append({
                    "entity_id": name,
                    "label": name,
                    "description": description,
                })

        return entities


# ------------------------------------------------------------------ #
# Module-level singleton cache (one per memory_dir)                  #
# ------------------------------------------------------------------ #

_linker_cache: dict[str, GLinkerEntityLinker] = {}
_cache_lock = threading.Lock()


def get_entity_linker(memory_dir: str, config: dict) -> Optional[GLinkerEntityLinker]:
    """
    Return a cached GLinkerEntityLinker for the given memory directory.
    Returns None if entity_glinker_enabled is not set in config.
    """
    if not config.get("entity_glinker_enabled", False):
        return None

    key = str(Path(memory_dir).resolve())
    with _cache_lock:
        if key not in _linker_cache:
            _linker_cache[key] = GLinkerEntityLinker(memory_dir, config)
        return _linker_cache[key]
