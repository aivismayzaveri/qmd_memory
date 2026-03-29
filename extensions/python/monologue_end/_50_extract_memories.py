from helpers import errors, plugins
from helpers.extension import Extension
from helpers.dirty_json import DirtyJson
from helpers.print_style import PrintStyle
from helpers.defer import DeferredTask, THREAD_BACKGROUND
from agent import LoopData
from helpers.log import LogItem

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client, session_log
from usr.plugins.qmd_memory.helpers.session_log import count_user_chars
from usr.plugins.qmd_memory.helpers.entity_linker import get_entity_linker


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
            categories = config.get("memory_extract_categories", ["entities", "episodes", "facts", "knowledge", "procedure", "goals", "guardrails"])
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
                            self._process_procedure(entry, epoch, memory_dir, config)
                        elif category == "goals":
                            self._process_goal(entry, epoch, memory_dir)
                        elif category == "guardrails":
                            self._process_guardrail(entry, memory_dir)
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
            context = entry.get("context", "")
            entity_type = entry.get("type", "")

            # Tier 1: fuzzy string match (catches case variants, partial names).
            # Returns canonical_name — the name as stored in the file.
            fuzzy_threshold = int(config.get("entity_fuzzy_threshold", 82))
            subfile, existing, canonical_name = memory_files.find_entity_fuzzy(
                memory_dir, name, threshold=fuzzy_threshold
            )

            if subfile and canonical_name:
                memory_files.update_entity(memory_dir, canonical_name, context, epoch)
                return

            # Tier 2: GLinker semantic linking (catches "aivismayzaveri" → "Vismay Zaveri").
            # Only runs if entity_glinker_enabled: true in config.
            linker = get_entity_linker(memory_dir, config)
            if linker:
                canonical_name, confidence = linker.find_canonical(name, context, entity_type)
                if canonical_name:
                    memory_files.update_entity(memory_dir, canonical_name, context, epoch)
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

        fact_category = entry.get("category", "general")
        if fact_category == "knowledge":
            self._process_knowledge(
                {"title": content[:60].rstrip(), "content": content, "source": ""},
                epoch, memory_dir
            )
            return

        # Dedup: line-by-line scan of the existing facts file.
        # The old approach (QMD search > 0.85 against the whole file) never worked
        # because a single new bullet line scores far below 0.85 against 200+ lines.
        try:
            existing_text = memory_files.read_category(memory_dir, "facts")
            content_norm = content.lower().rstrip(".")
            for line in existing_text.splitlines():
                # Skip metadata lines and headings
                line_clean = line.strip().lstrip("- ").lower().rstrip(".")
                if not line_clean or line_clean.startswith("#") or line_clean.startswith("**updated") or line_clean.startswith("_ref"):
                    continue
                # Skip YAML frontmatter lines
                if line_clean.startswith("schema_version") or line_clean.startswith("type:") or line_clean.startswith("last_updated"):
                    continue
                # Substring match in either direction catches paraphrases and exact duplicates
                if content_norm in line_clean or line_clean in content_norm:
                    return  # Already stored
        except Exception:
            pass  # Graceful — append on any error

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

    def _process_procedure(self, entry: dict, epoch: str, memory_dir: str, config: dict = None):
        if not isinstance(entry, dict):
            return
        title = entry.get("title", "Procedure").strip()
        problem = entry.get("problem", "")
        steps = entry.get("steps", [])
        entities = entry.get("entities", [])
        today = memory_files._now_iso()

        # Dedup: exact heading match first
        if memory_files.find_entry(memory_dir, "procedure", title):
            return

        # Dedup: QMD similarity against procedure category only (catches same procedure
        # with a different title, which is the main failure mode here)
        if config:
            try:
                search_query = f"{title} {problem}"[:120]
                results = qmd_client.search(search_query, config, limit=3)
                for r in results:
                    if "procedure" in r.get("path", "").lower() or "Procedure" in r.get("file", ""):
                        if float(r.get("score", 0)) > 0.75:
                            return  # Near-identical procedure already exists
            except Exception:
                pass

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

        # Goals are stored as bullet points ("- [ ] **Title** — desc"), NOT as ## headings.
        # find_entry() searches for ## headings and will NEVER find a goal.
        # Scan the raw file content for the title pattern instead.
        goals_text = memory_files.read_category(memory_dir, "goals")
        title_pattern = re.compile(rf'\*\*{re.escape(title)}\*\*', re.IGNORECASE)
        if title_pattern.search(goals_text):
            # Goal already exists. If completing, rewrite the line to checked.
            if status == "completed":
                memory_files.mark_goal_completed(memory_dir, title, today, epoch)
            return

        checkbox = "[x]" if status == "completed" else "[ ]"
        goal_text = (
            f"- {checkbox} **{title}** — {description}\n"
            f"  _Updated: {today}. Ref: [session](sessions/{epoch}.md)_"
        )
        section = "Completed" if status == "completed" else "Active"
        memory_files.append_to_section(memory_dir, "goals", section, goal_text)


    def _process_guardrail(self, entry: dict, memory_dir: str):
        """
        Append a guardrail entry to the appropriate ## section in Guardrails.md.
        Skips if near-identical content already exists to prevent duplication.
        """
        if not isinstance(entry, dict):
            return
        section = entry.get("section", "Other").strip()
        content = entry.get("content", "").strip()
        if not content:
            return

        # Valid sections — normalize input to closest match
        valid_sections = ["Identity", "Interaction Preferences", "Code Style", "Security", "Reminders", "Other"]
        matched_section = next(
            (s for s in valid_sections if s.lower() == section.lower()),
            "Other"
        )

        # Dedup: skip if the same or very similar content already exists in Guardrails.md
        existing = memory_files.get_guardrails_text(memory_dir)
        content_norm = content.lower().rstrip(".")
        for line in existing.splitlines():
            line_clean = line.strip().lstrip("- ").lower().rstrip(".")
            if not line_clean:
                continue
            # Substring match in either direction covers paraphrases and exact duplicates
            if content_norm in line_clean or line_clean in content_norm:
                return

        today = memory_files._now_iso()
        guardrail_line = f"- {content}\n  - _Updated: {today}_"
        memory_files.append_to_section(memory_dir, "guardrails", matched_section, guardrail_line)


def _extract_heading_from_snippet(snippet: str) -> str:
    """Try to extract a ## heading from a QMD result snippet."""
    import re
    match = re.search(r'^## (.+)$', snippet, re.MULTILINE)
    return match.group(1).strip() if match else ""
