from helpers import errors, plugins
from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers.defer import DeferredTask, THREAD_BACKGROUND
from agent import LoopData
from helpers.log import LogItem

from usr.plugins.qmd_memory.helpers import qmd_client, session_log
from usr.plugins.qmd_memory.helpers.session_log import count_user_chars


class ExtractMemories(Extension):

    def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config or not config.get("memory_extract_enabled", True):
            return

        log_item = self.agent.context.log.log(
            type="util",
            heading="Extracting memories...",
        )

        task = DeferredTask(thread_name=THREAD_BACKGROUND)
        task.start_task(self.extract, loop_data, log_item)

    async def extract(self, loop_data: LoopData, log_item: LogItem, **kwargs):
        if not self.agent:
            return

        try:
            config = plugins.get_plugin_config("qmd_memory", self.agent)
            if not config:
                return

            memory_dir = config.get("memory_dir", "/a0/usr/memory")

            # Get conversation history
            history_text = self.agent.concat_messages(self.agent.history)
            tool_call_count = session_log.count_tool_calls(self.agent.history)
            user_chars = count_user_chars(self.agent.history)

            # Check minimum threshold
            if not session_log.should_create_log(history_text, tool_call_count, config, user_chars):
                log_item.update(heading="Conversation too short — skipping memory extraction")
                return

            # Call utility LLM for session summary
            try:
                sys_prompt = self.agent.read_prompt("extraction.system.md")
                message = self.agent.read_prompt("extraction.message.md", history=history_text)
                summary = await self.agent.call_utility_model(
                    system=sys_prompt,
                    message=message,
                    background=True,
                )
            except Exception as e:
                log_item.update(heading=f"Extraction LLM call failed: {str(e)[:100]}")
                return

            if not summary or not isinstance(summary, str) or not summary.strip():
                log_item.update(heading="No response from extraction model")
                return

            summary = summary.strip()

            # Create session log
            epoch = await session_log.create_session_log(
                self.agent, summary, memory_dir, config
            )

            if not epoch:
                log_item.update(heading="Failed to create session log")
                return

            # Trigger reindex
            try:
                qmd_client.reindex_async(config)
            except Exception as e:
                PrintStyle.warning(f"[QMD Memory] Reindex trigger failed: {e}")

            log_item.update(
                heading=f"Session log created: {epoch}",
                result=f"Session log: {epoch}",
            )

        except Exception as e:
            err = errors.format_error(e)
            log_item.update(heading="Memory extraction error", content=err)
