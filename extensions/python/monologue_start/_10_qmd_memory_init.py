from helpers.extension import Extension
from helpers import plugins
from helpers.print_style import PrintStyle
from agent import LoopData
from pathlib import Path

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client


class QmdMemoryInit(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return

        memory_dir = self._resolve_memory_dir(config)

        # Ensure directory structure exists
        try:
            memory_files.ensure_memory_structure(memory_dir)
        except Exception as e:
            PrintStyle.warning(f"[QMD Memory] Failed to ensure memory structure: {e}")

        # Register memory dir as QMD collection (idempotent)
        try:
            if qmd_client.add_collection(memory_dir, config):
                # Register context description so QMD can guide LLM relevance decisions
                qmd_client.add_context(
                    qmd_client.MEMORY_COLLECTION_NAME,
                    qmd_client.MEMORY_COLLECTION_CONTEXT,
                    config,
                )
            else:
                PrintStyle.warning("[QMD Memory] QMD collection registration failed — search may be unavailable")
        except Exception as e:
            PrintStyle.warning(f"[QMD Memory] Collection registration error: {e}")

        # Register any extra paths configured by the user
        extra_paths = config.get("memory_extra_paths", [])
        if isinstance(extra_paths, list):
            for extra_path in extra_paths:
                try:
                    p = Path(extra_path)
                    if p.exists():
                        if not qmd_client.add_collection(str(p), config):
                            PrintStyle.warning(f"[QMD Memory] Failed to register extra path: {extra_path}")
                    else:
                        PrintStyle.warning(f"[QMD Memory] Extra path does not exist: {extra_path}")
                except Exception as e:
                    PrintStyle.warning(f"[QMD Memory] Extra path error ({extra_path}): {e}")

        # Trigger background reindex
        try:
            qmd_client.reindex_async(config)
        except Exception as e:
            PrintStyle.warning(f"[QMD Memory] Reindex trigger failed: {e}")

    def _resolve_memory_dir(self, config: dict) -> str:
        """Resolve the effective memory directory, supporting per-agent isolation."""
        base_dir = config.get("memory_dir", "/a0/usr/memory")
        if config.get("memory_per_agent", False) and self.agent:
            agent_num = getattr(self.agent, "number", 0)
            # Agent 0 (main agent) uses the base dir; sub-agents get their own subfolder
            if agent_num > 0:
                return str(Path(base_dir) / "agents" / f"agent_{agent_num}")
        return base_dir
