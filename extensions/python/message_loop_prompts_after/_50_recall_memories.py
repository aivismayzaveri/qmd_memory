import asyncio
import os

from helpers import errors, plugins
from helpers.extension import Extension
from helpers.print_style import PrintStyle
from agent import LoopData
from helpers.log import LogItem

from usr.plugins.qmd_memory.helpers import qmd_client

DATA_NAME_TASK = "_qmd_recall_task"
DATA_NAME_ITER = "_qmd_recall_iter"
SEARCH_TIMEOUT = 30


class RecallMemories(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return

        if not config.get("memory_recall_enabled", True):
            return

        interval = int(config.get("memory_recall_interval", 3))
        if loop_data.iteration % interval != 0:
            self.agent.set_data(DATA_NAME_TASK, None)
            self.agent.set_data(DATA_NAME_ITER, loop_data.iteration)
            return

        log_item = self.agent.context.log.log(
            type="util",
            heading="Searching memories...",
        )

        try:
            task = asyncio.create_task(
                asyncio.wait_for(
                    self.search_memories(loop_data=loop_data, log_item=log_item, config=config),
                    timeout=SEARCH_TIMEOUT,
                )
            )
        except Exception as e:
            log_item.update(heading=f"Memory recall failed: {str(e)[:100]}")
            task = None

        self.agent.set_data(DATA_NAME_TASK, task)
        self.agent.set_data(DATA_NAME_ITER, loop_data.iteration)

    async def search_memories(self, loop_data: LoopData, log_item: LogItem, config: dict, **kwargs):
        if not self.agent:
            return

        # Clear previous memories from context
        extras = loop_data.extras_persistent
        if "memories" in extras:
            del extras["memories"]

        try:
            user_msg = loop_data.user_message.output_text() if loop_data.user_message else ""
            history_len = int(config.get("memory_recall_history_len", 10000))
            history = self.agent.history.output_text()[-history_len:]

            if config.get("memory_recall_query_prep", False):
                try:
                    system = self.agent.read_prompt("recall.query.sys.md")
                    message = self.agent.read_prompt(
                        "recall.query.msg.md", history=history, message=user_msg
                    )
                    query = await self.agent.call_utility_model(system=system, message=message)
                    query = query.strip() if query else ""
                    log_item.update(query=query)
                except Exception as e:
                    PrintStyle.warning(f"[QMD Memory] Query prep failed: {e}")
                    query = user_msg + "\n\n" + history
            else:
                query = user_msg + "\n\n" + history

            if not query or len(query) <= 3:
                log_item.update(heading="No query to search memories")
                return

            # Search QMD
            limit = int(config.get("memory_recall_max_results", 8))
            results = qmd_client.search(query, config, limit=limit)

            if not results:
                log_item.update(heading="No memories found")
                return

            # Format results within token budget
            token_budget = int(config.get("memory_recall_token_budget", 3000))
            memories_text = self._format_results(results, token_budget)

            if not memories_text:
                log_item.update(heading="No relevant memories after formatting")
                return

            log_item.update(
                heading=f"{len(results)} memories found",
                memories=memories_text,
            )

            extras["memories"] = self.agent.parse_prompt(
                "agent.system.memories.md", memories=memories_text
            )

        except Exception as e:
            err = errors.format_error(e)
            log_item.update(heading="Memory recall error", content=err)

    @staticmethod
    def _strip_qmd_scheme(path: str) -> str:
        """Strip the qmd:// URI scheme if present."""
        if path.startswith("qmd://"):
            return path[6:]
        return path

    def _format_results(self, results: list, token_budget: int) -> str:
        """Format QMD results into markdown, respecting token budget (1 token ≈ 4 chars)."""
        char_budget = token_budget * 4
        parts = []
        used = 0

        _FOLDER_CATS = {"entities", "sessions", "docs"}

        for r in results:
            path = self._strip_qmd_scheme(r.get("path", r.get("file", "")))
            title = r.get("title", "")
            snippet = r.get("snippet", "")

            # Derive category label from path parts (works with qmd:// stripped paths)
            path_parts = [p for p in path.replace("\\", "/").split("/") if p]
            if len(path_parts) >= 2 and path_parts[-2] in _FOLDER_CATS:
                cat_label = path_parts[-2]
            elif path_parts:
                cat_label = path_parts[-1].rsplit(".", 1)[0]
            else:
                cat_label = "memory"

            entry = f"**[{cat_label}]** {title}\n{snippet}"
            if used + len(entry) > char_budget:
                break

            parts.append(entry)
            used += len(entry)

        return "\n\n---\n\n".join(parts) if parts else ""
