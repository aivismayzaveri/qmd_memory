from helpers.extension import Extension
from helpers import plugins
from helpers.print_style import PrintStyle
from agent import LoopData

from usr.plugins.qmd_memory.helpers import memory_files


class GuardrailsPrompt(Extension):

    async def execute(self, system_prompt: list = [], loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config or not config.get("guardrails_enabled", True):
            return

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        try:
            guardrails_text = memory_files.get_guardrails_text(memory_dir)
            if guardrails_text.strip():
                prompt = self.agent.read_prompt("agent.system.guardrails.md", guardrails=guardrails_text)
                system_prompt.insert(0, prompt)
        except Exception as e:
            PrintStyle.warning(f"[QMD Memory] Failed to load guardrails: {e}")
