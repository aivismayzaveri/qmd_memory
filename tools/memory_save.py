from helpers.tool import Tool, Response
from helpers import plugins

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client, entity_linker


class MemorySave(Tool):

    async def execute(self, category="facts", content="", heading="", **kwargs) -> Response:
        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        valid_categories = ["entities", "episodes", "facts", "procedure", "goals", "guardrails", "knowledge"]
        if category not in valid_categories:
            return Response(
                message=f"Invalid category '{category}'. Choose from: {', '.join(valid_categories)}",
                break_loop=False,
            )

        if not content:
            return Response(message="Content is required.", break_loop=False)

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        try:
            if category == "entities":
                # Parse entity from content/heading
                entity = {
                    "name": heading or "Unknown",
                    "type": "other",
                    "context": content,
                }
                # Check dedup using full 3-tier system: exact → fuzzy → GLinker
                if config.get("entity_dedup_enabled", True):
                    threshold = int(config.get("entity_fuzzy_threshold", 82))
                    subfile, existing, canonical = memory_files.find_entity_fuzzy(
                        memory_dir, entity["name"], threshold=threshold,
                    )
                    # Tier 3: GLinker semantic linking (if enabled and no fuzzy match)
                    if not subfile:
                        linker = entity_linker.get_entity_linker(memory_dir, config)
                        if linker:
                            canonical_gl, conf = linker.find_canonical(
                                entity["name"], context=content, entity_type=entity["type"],
                            )
                            if canonical_gl:
                                subfile, existing = memory_files.find_entity(memory_dir, canonical_gl)
                                canonical = canonical_gl

                    if subfile and canonical:
                        memory_files.update_entity(memory_dir, canonical, content)
                        result = self.agent.read_prompt(
                            "fw.memory_updated.md", category=category,
                            heading=f"{heading} (matched: {canonical})" if canonical != entity["name"] else heading,
                        )
                        qmd_client.reindex_async(config)
                        return Response(message=result, break_loop=False)
                memory_files.append_entity(memory_dir, entity)
            elif category == "guardrails":
                # Append to guardrails
                existing = memory_files.get_guardrails_text(memory_dir)
                memory_files.write_guardrails(memory_dir, existing + f"\n\n## Manual Entry\n- {content}")
            else:
                # Format the entry with heading if provided
                if heading:
                    entry = f"## {heading}\n{content}"
                else:
                    entry = content
                memory_files.append_to_category(memory_dir, category, entry)

            qmd_client.reindex_async(config)

        except Exception as e:
            return Response(
                message=f"Failed to save memory: {e}",
                break_loop=False,
            )

        result = self.agent.read_prompt("fw.memory_saved.md", category=category, heading=heading or content[:50])
        return Response(message=result, break_loop=False)
