"""File search tools: grep and glob."""

import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.filesystem import _resolve_path

_BINARY_EXT = frozenset({".png", ".jpg", ".pdf", ".zip", ".pyc", ".doc", ".docx", ".xlsx"})
_MAX = 200
_MAX_SIZE = 2 * 1024 * 1024


def _text_file(p: Path) -> bool:
    if p.suffix.lower() in _BINARY_EXT:
        return False
    try:
        return p.stat().st_size <= _MAX_SIZE
    except OSError:
        return False


def _rel(t: Path, r: Path) -> str:
    try:
        return str(t.relative_to(r))
    except ValueError:
        return str(t)


class GrepSearchTool(Tool):
    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "grep_search"

    @property
    def description(self) -> str:
        return "Search file contents by pattern (grep-like). Output: path:line_no: content. Use is_regex for regex, context_lines for lines around match."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search string or regex"},
                "path": {"type": "string", "description": "File or directory to search"},
                "is_regex": {"type": "boolean", "default": False},
                "case_sensitive": {"type": "boolean", "default": True},
                "context_lines": {"type": "integer", "default": 0},
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str | None = None, is_regex: bool = False, case_sensitive: bool = True, context_lines: int = 0, **kwargs: Any) -> str:
        if not pattern:
            return "Error: No pattern provided."
        root = _resolve_path(path, self._workspace, self._allowed_dir) if path else (self._workspace or Path(".").resolve())
        if not root.exists():
            return f"Error: Path {root} does not exist."
        fl = 0 if case_sensitive else re.IGNORECASE
        try:
            rx = re.compile(pattern, fl) if is_regex else re.compile(re.escape(pattern), fl)
        except re.error as e:
            return f"Error: Invalid regex: {e}"
        out = []
        single = root.is_file()
        files = [root] if single else sorted(f for f in root.rglob("*") if f.is_file() and _text_file(f))
        for fp in files:
            if len(out) >= _MAX:
                break
            try:
                lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    lo = max(0, i - 1 - context_lines)
                    hi = min(len(lines), i + context_lines)
                    rel = fp.name if single else _rel(fp, root)
                    for j in range(lo, hi):
                        p = ">" if j == i - 1 else " "
                        out.append(f"{rel}:{j + 1}:{p} {lines[j]}")
                    if context_lines:
                        out.append("---")
                    if len(out) >= _MAX:
                        break
        if not out:
            return f"No matches for: {pattern}"
        return "\n".join(out) + ("\n(Truncated.)" if len(out) >= _MAX else "")


class GlobSearchTool(Tool):
    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "glob_search"

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern (e.g. *.py, **/*.json)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "path": {"type": "string", "description": "Root directory"},
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str | None = None, **kwargs: Any) -> str:
        if not pattern:
            return "Error: No pattern provided."
        root = _resolve_path(path, self._workspace, self._allowed_dir) if path else (self._workspace or Path(".").resolve())
        if not root.exists() or not root.is_dir():
            return f"Error: {root} is not a directory or does not exist."
        try:
            res = sorted(root.glob(pattern))
            out = [f"{_rel(e, root)}{'/' if e.is_dir() else ''}" for e in res[: _MAX]]
            return "\n".join(out) + ("\n(Truncated.)" if len(res) > _MAX else "") if out else f"No files matched: {pattern}"
        except Exception as e:
            return f"Error: {e}"
