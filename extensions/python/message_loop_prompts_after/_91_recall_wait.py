from helpers.extension import Extension
from helpers import plugins
from agent import LoopData

# These must match the constants in _50_recall_memories.py
DATA_NAME_TASK = "_qmd_recall_task"
DATA_NAME_ITER = "_qmd_recall_iter"


class RecallWait(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return

        task = self.agent.get_data(DATA_NAME_TASK)
        iter_num = self.agent.get_data(DATA_NAME_ITER) or 0

        if task and not task.done():
            if config.get("memory_recall_delayed", False):
                if iter_num == loop_data.iteration:
                    delay_text = self.agent.read_prompt("recall.delay_msg.md")
                    loop_data.extras_temporary["qmd_memory_recall_delayed"] = delay_text
                    return
            await task
