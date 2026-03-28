"""
memory_import — Import an external document into the memory docs/ folder.

Accepts a file path. Reads the file, converts to markdown if needed,
saves to docs/<date>_<slug>.md, updates the docs index, triggers reindex.
"""
from pathlib import Path
from helpers.tool import Tool, Response
from helpers import plugins
from helpers.print_style import PrintStyle

from usr.plugins.qmd_memory.helpers import memory_files, qmd_client


class MemoryImport(Tool):

    async def execute(self, path: str = "", title: str = "", tags: str = "", **kwargs) -> Response:
        if not self.agent:
            return Response(message="No agent context.", break_loop=False)

        config = plugins.get_plugin_config("qmd_memory", self.agent)
        if not config:
            return Response(message="QMD Memory plugin not configured.", break_loop=False)

        if not path:
            return Response(message="path parameter is required.", break_loop=False)

        file_path = Path(path)
        if not file_path.exists():
            return Response(message=f"File not found: {path}", break_loop=False)

        # Read and convert content
        try:
            content = self._read_as_markdown(file_path)
        except Exception as e:
            return Response(message=f"Failed to read file: {e}", break_loop=False)

        # Use filename as title if not provided
        if not title:
            title = file_path.stem.replace("-", " ").replace("_", " ").title()

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        memory_dir = config.get("memory_dir", "/a0/usr/memory")

        try:
            filename = memory_files.save_doc(
                memory_dir=memory_dir,
                title=title,
                content=content,
                source=str(file_path),
                tags=tag_list,
            )
        except Exception as e:
            return Response(message=f"Failed to save document: {e}", break_loop=False)

        # Trigger reindex
        try:
            qmd_client.reindex_async(config)
        except Exception as e:
            PrintStyle.warning(f"[QMD Memory] Reindex after import failed: {e}")

        word_count = len(content.split())
        return Response(
            message=f"Document imported: `docs/{filename}` ({word_count} words). "
                    f"It is now searchable via memory_search.",
            break_loop=False,
        )

    def _read_as_markdown(self, file_path: Path) -> str:
        """Read a file and return markdown string."""
        suffix = file_path.suffix.lower()

        if suffix in (".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"):
            return file_path.read_text(encoding="utf-8", errors="replace")

        if suffix == ".pdf":
            return self._read_pdf(file_path)

        if suffix in (".html", ".htm"):
            return self._read_html(file_path)

        # Fallback: try reading as text
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise ValueError(f"Unsupported file type '{suffix}' and could not read as text: {e}")

    def _read_pdf(self, file_path: Path) -> str:
        """Extract text from PDF using pdfminer if available."""
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(str(file_path))
            if text and text.strip():
                return text
        except ImportError:
            pass

        # Fallback: pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(p for p in pages if p.strip())
        except ImportError:
            raise ValueError(
                "PDF reading requires pdfminer.six or pypdf. "
                "Install with: pip install pdfminer.six"
            )

    def _read_html(self, file_path: Path) -> str:
        """Convert HTML to markdown-ish text."""
        try:
            import markdownify
            html = file_path.read_text(encoding="utf-8", errors="replace")
            return markdownify.markdownify(html, heading_style="ATX")
        except ImportError:
            pass

        # Fallback: strip tags
        import re
        html = file_path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r'<[^>]+>', ' ', html)
        return re.sub(r'\s+', ' ', text).strip()
