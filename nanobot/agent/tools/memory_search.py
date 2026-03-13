"""Memory search tool: search MEMORY.md and memory/*.md by text."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.utils.helpers import ensure_dir


class MemorySearchTool(Tool):
    """Search long-term memory files (MEMORY.md, memory/*.md) by query string."""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._memory_dir = ensure_dir(workspace / "memory")

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search MEMORY.md and memory/*.md for relevant snippets. "
            "Use before answering questions about prior work, decisions, dates, people, preferences. "
            "Returns matching lines with file path and line number."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (substring match, case-insensitive)"},
                "max_results": {"type": "integer", "description": "Max results to return", "default": 20},
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 20, **kwargs: Any) -> str:
        if not query:
            return "Error: No query provided."
        q = query.lower()
        out = []
        seen = set()
        files = []
        if (self._memory_dir / "MEMORY.md").exists():
            files.append(self._memory_dir / "MEMORY.md")
            seen.add(self._memory_dir / "MEMORY.md")
        if self._memory_dir.exists():
            for fp in self._memory_dir.glob("*.md"):
                if fp not in seen:
                    files.append(fp)
                    seen.add(fp)
        for fp in files:
            if not fp.is_file():
                continue
            try:
                lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            rel = fp.name
            for i, line in enumerate(lines, 1):
                if q in line.lower():
                    out.append(f"{rel}:{i}: {line.strip()}")
                    if len(out) >= max_results:
                        return "\n".join(out) + "\n(Truncated.)"
        return "\n".join(out) if out else f"No matches for query: {query}"
