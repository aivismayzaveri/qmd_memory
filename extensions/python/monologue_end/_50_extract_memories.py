from helpers import errors, plugins
from helpers.extension import Extension
from helpers.dirty_json import DirtyJson
from helpers.print_style import PrintStyle
from helpers.defer import DeferredTask, THREAD_BACKGROUND
from agent import LoopData
from helpers.log import LogItem

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client, session_log
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

            # Check minimum threshold — skip trivial conversations
            # Uses user message length, not total history (AI responses are always long)
            if not session_log.should_create_log(history_text, tool_call_count, config, user_chars):
                log_item.update(heading="Conversation too short — skipping memory extraction")
                return

            # Call utility LLM for extraction
            try:
                sys_prompt = self.agent.read_prompt("extraction.system.md")
                message = self.agent.read_prompt("extraction.message.md", history=history_text)
                result_json = await self.agent.call_utility_model(
                    system=sys_prompt,
                    message=message,
                    background=True,
                )
            except Exception as e:
                log_item.update(heading=f"Extraction LLM call failed: {str(e)[:100]}")
                return

            if not result_json or not isinstance(result_json, str) or not result_json.strip():
                log_item.update(heading="No response from extraction model")
                return

            try:
                extraction = DirtyJson.parse_string(result_json.strip())
            except Exception as e:
                log_item.update(heading=f"Failed to parse extraction JSON: {str(e)[:100]}")
                return

            if not isinstance(extraction, dict):
                log_item.update(heading="Extraction result is not a dict")
                return

            log_item.update(content=result_json[:2000])

            # Create session log
            epoch = await session_log.create_session_log(
                self.agent, history_text, extraction, memory_dir, config
            )

            if not epoch:
                log_item.update(heading="Failed to create session log")
                return

            # Process each category
            categories = config.get("memory_extract_categories", ["entities", "episodes", "facts", "knowledge", "procedure", "goals"])
            saved = []

            for category in categories:
                entries = extraction.get(category, [])
                if not entries:
                    continue

                for entry in entries:
                    try:
                        if category == "entities":
                            await self._process_entity(entry, epoch, memory_dir, config)
                        elif category == "facts":
                            await self._process_fact(entry, epoch, memory_dir, config)
                        elif category == "knowledge":
                            self._process_knowledge(entry, epoch, memory_dir)
                        elif category == "episodes":
                            self._process_episode(entry, epoch, memory_dir)
                        elif category == "procedure":
                            self._process_procedure(entry, epoch, memory_dir)
                        elif category == "goals":
                            self._process_goal(entry, epoch, memory_dir)
                        saved.append(category)
                    except Exception as e:
                        PrintStyle.warning(f"[QMD Memory] Error processing {category}: {e}")

            # Check if any files need splitting
            for cat in ["episodes", "facts", "knowledge", "procedure", "goals"]:
                try:
                    threshold = int(config.get("auto_split_threshold_lines", 500))
                    memory_files.check_and_split(memory_dir, cat, threshold)
                except Exception as e:
                    PrintStyle.warning(f"[QMD Memory] Auto-split check for {cat}: {e}")

            # Trigger reindex
            try:
                qmd_client.reindex_async(config)
            except Exception as e:
                PrintStyle.warning(f"[QMD Memory] Reindex trigger failed: {e}")

            cats_summary = ", ".join(sorted(set(saved))) if saved else "none"
            log_item.update(
                heading=f"Memories extracted: {len(saved)} entries ({cats_summary})",
                result=f"Session log: {epoch}",
            )

        except Exception as e:
            err = errors.format_error(e)
            log_item.update(heading="Memory extraction error", content=err)

    async def _process_entity(self, entry: dict, epoch: str, memory_dir: str, config: dict):
        if not isinstance(entry, dict):
            return
        name = entry.get("name", "").strip()
        if not name:
            return

        if config.get("entity_dedup_enabled", True):
            subfile, existing = memory_files.find_entity(memory_dir, name)
            if subfile:
                new_context = entry.get("context", "")
                memory_files.update_entity(memory_dir, name, new_context, epoch)
                return

        memory_files.append_entity(memory_dir, entry, epoch)

    async def _process_fact(self, entry, epoch: str, memory_dir: str, config: dict):
        if isinstance(entry, str):
            entry = {"content": entry, "category": "general"}
        if not isinstance(entry, dict):
            return

        content = entry.get("content", "").strip()
        if not content:
            return

        # Contradiction check via QMD similarity search
        try:
            results = qmd_client.search(content, config, limit=3)
            for r in results:
                path = r.get("path", "")
                score = float(r.get("score", 0))
                if "Facts" in path and score > 0.85:
                    snippet = r.get("snippet", "")
                    existing_heading = _extract_heading_from_snippet(snippet)
                    if existing_heading and memory_files.find_entry(memory_dir, "facts", existing_heading):
                        memory_files.update_entry(memory_dir, "facts", existing_heading, content)
                        return
        except Exception:
            pass  # Graceful — just append on any error

        fact_category = entry.get("category", "general")
        # "knowledge" category facts go to Knowledge.md via the knowledge processor — skip here
        if fact_category == "knowledge":
            self._process_knowledge(
                {"title": content[:60].rstrip(), "content": content, "source": ""},
                epoch, memory_dir
            )
            return

        section_map = {
            "user_preference": "User Preferences",
            "project_info": "Project Information",
            "reference": "References & Links",
        }
        section = section_map.get(fact_category, "General")
        fact_line = (
            f"- {content}\n"
            f"  - **Updated:** {memory_files._now_iso()}\n"
            f"  - _Ref: [session](sessions/{epoch}.md)_"
        )
        memory_files.append_to_section(memory_dir, "facts", section, fact_line)

    def _process_knowledge(self, entry: dict, epoch: str, memory_dir: str):
        if not isinstance(entry, dict):
            return
        title = entry.get("title", "").strip()
        if not title:
            return
        content = entry.get("content", "")
        source = entry.get("source", "")
        today = memory_files._now_iso()

        # Dedup: skip if heading already exists
        if memory_files.find_entry(memory_dir, "knowledge", title):
            # Update existing entry with latest content
            memory_files.update_entry(memory_dir, "knowledge", title, content)
            return

        knowledge_text = (
            f"## {title}\n"
            f"{content.strip()}\n"
            + (f"- **Source:** {source}\n" if source else "")
            + f"- **Updated:** {today}\n"
            f"- _Ref: [session](sessions/{epoch}.md)_"
        )
        memory_files.append_to_category(memory_dir, "knowledge", knowledge_text, "")

    def _process_episode(self, entry: dict, epoch: str, memory_dir: str):
        if not isinstance(entry, dict):
            return
        title = entry.get("title", "Episode").strip()
        valid_time = entry.get("valid_time", memory_files._now_iso())
        description = entry.get("description", "")
        resolution = entry.get("resolution", "")
        entities = entry.get("entities", [])
        today = memory_files._now_iso()

        # Dedup: if an episode with this title already exists, update instead of append
        if memory_files.find_entry(memory_dir, "episodes", title):
            updated_body = (
                f"- **Valid from**: {valid_time} _(when the event actually happened)_\n"
                f"- **Recorded at**: {today} _(when we learned about it)_\n"
                f"- **Entities**: {', '.join(entities) if entities else 'none'}\n"
                f"- **Description**: {description}\n"
                f"- **Resolution**: {resolution}\n"
                f"- **Updated:** {today}\n"
                f"- _Ref: [session](sessions/{epoch}.md)_"
            )
            memory_files.update_entry(memory_dir, "episodes", title, updated_body)
            return

        episode_text = (
            f"## {title}\n"
            f"- **Valid from**: {valid_time} _(when the event actually happened)_\n"
            f"- **Recorded at**: {today} _(when we learned about it)_\n"
            f"- **Entities**: {', '.join(entities) if entities else 'none'}\n"
            f"- **Description**: {description}\n"
            f"- **Resolution**: {resolution}\n"
            f"- **Updated:** {today}\n"
            f"- _Ref: [session](sessions/{epoch}.md)_"
        )
        memory_files.append_to_category(memory_dir, "episodes", episode_text, "")

    def _process_procedure(self, entry: dict, epoch: str, memory_dir: str):
        if not isinstance(entry, dict):
            return
        title = entry.get("title", "Procedure").strip()
        problem = entry.get("problem", "")
        steps = entry.get("steps", [])
        entities = entry.get("entities", [])
        today = memory_files._now_iso()

        steps_text = "\n".join([f"  {i+1}. {s}" for i, s in enumerate(steps)])
        proc_text = (
            f"## {title}\n"
            f"- **Problem**: {problem}\n"
            f"- **Steps**:\n{steps_text}\n"
            f"- **Entities**: {', '.join(entities) if entities else 'none'}\n"
            f"- **Updated:** {today}\n"
            f"- _Ref: [session](sessions/{epoch}.md)_"
        )
        memory_files.append_to_category(memory_dir, "procedure", proc_text, "")

    def _process_goal(self, entry: dict, epoch: str, memory_dir: str):
        if not isinstance(entry, dict):
            return
        title = entry.get("title", "Goal").strip()
        status = entry.get("status", "active")
        description = entry.get("description", "")
        today = memory_files._now_iso()

        checkbox = "[x]" if status == "completed" else "[ ]"
        goal_text = (
            f"- {checkbox} **{title}** — {description}\n"
            f"  _Updated: {today}. Ref: [session](sessions/{epoch}.md)_"
        )

        existing = memory_files.find_entry(memory_dir, "goals", title)
        if existing:
            memory_files.update_entry(
                memory_dir, "goals", title,
                f"{'**Status:** completed' if status == 'completed' else '**Status:** active'}\n{description}"
            )
            return

        section = "Completed" if status == "completed" else "Active"
        memory_files.append_to_section(memory_dir, "goals", section, goal_text)


def _extract_heading_from_snippet(snippet: str) -> str:
    """Try to extract a ## heading from a QMD result snippet."""
    import re
    match = re.search(r'^## (.+)$', snippet, re.MULTILINE)
    return match.group(1).strip() if match else ""
