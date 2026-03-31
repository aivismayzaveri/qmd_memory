"""
Pre-compaction memory flush reminder.
When conversation history grows very long, reminds the agent to save important
things to memory before context compaction discards them.
"""
from helpers.extension import Extension
from helpers import plugins
from agent import LoopData


class PrecompactCheck(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config or not config.get("memory_precompact_enabled", True):
            return

        threshold = int(config.get("memory_precompact_threshold_chars", 40000))

        try:
            history_text = self.agent.concat_messages(self.agent.history)
        except Exception:
            return

        if len(history_text) < threshold:
            return

        # Only remind once — check if we already injected this turn
        if loop_data.extras_temporary.get("precompact_warned"):
            return

        loop_data.extras_temporary["precompact_warned"] = True
        loop_data.extras_temporary["precompact_reminder"] = (
            "**Memory notice:** This conversation is getting long and may be compacted soon. "
            "A session summary will be saved automatically when the conversation ends."
        )
