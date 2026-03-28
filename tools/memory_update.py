from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client


class MemoryUpdate(Tool):

    async def execute(self, category="", heading="", content="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not category or not heading or not content:
            return Response(
                message="category, heading, and content are all required.",
                break_loop=False,
            )

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        try:
            if category == "entities":
                found = memory_files.update_entity(memory_dir, heading, content)
            else:
                found = memory_files.update_entry(memory_dir, category, heading, content)

            if not found:
                return Response(
                    message=f"Entry '{heading}' not found in {category}. Use memory_save to create it.",
                    break_loop=False,
                )

            qmd_client.reindex_async(config)

        except Exception as e:
            return Response(message=f"Failed to update memory: {e}", break_loop=False)

        result = self.agent.read_prompt("fw.memory_updated.md", category=category, heading=heading)
        return Response(message=result, break_loop=False)
