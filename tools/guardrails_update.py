from helpers.tool import Tool, Response
from helpers import plugins
from helpers.log import LogItem

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client


class GuardrailsUpdate(Tool):

    async def execute(self, adjustments="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not adjustments:
            return Response(message="Please describe the adjustments to make.", break_loop=False)

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        # Get current guardrails
        current_rules = memory_files.get_guardrails_text(memory_dir)

        # Log streaming
        async def log_callback(content):
            self.log.stream(ruleset=content)

        # Call utility LLM to merge adjustments
        try:
            system = self.agent.read_prompt("behaviour.merge.sys.md")
            msg = self.agent.read_prompt(
                "behaviour.merge.msg.md",
                current_rules=current_rules,
                adjustments=adjustments,
            )
            updated_rules = await self.agent.call_utility_model(
                system=system,
                message=msg,
                callback=log_callback,
            )
        except Exception as e:
            # Fallback: append the adjustment directly
            updated_rules = current_rules + f"\n\n## Added\n- {adjustments}"

        # Write updated guardrails
        try:
            memory_files.write_guardrails(memory_dir, updated_rules)
            qmd_client.reindex_async(config)
        except Exception as e:
            return Response(message=f"Failed to update guardrails: {e}", break_loop=False)

        result = self.agent.read_prompt("fw.memory_updated.md", category="guardrails", heading="rules")
        return Response(message=result, break_loop=False)
