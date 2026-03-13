"""Per-session todo list storage (OpenCode-style todowrite/todoread)."""

import json
from pathlib import Path

from nanobot.utils.helpers import ensure_dir


TodoItem = dict[str, str]  # content, status, priority


class TodoStore:
    """Persistent todo list per session key."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._dir = ensure_dir(workspace / "sessions")
        self._path = self._dir / "todos.json"
        self._cache: dict[str, list[TodoItem]] = {}

    def _safe_key(self, session_key: str) -> str:
        return session_key.replace(":", "_").replace("/", "_")

    def _load_all(self) -> dict[str, list[TodoItem]]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return {k: list(v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_all(self, data: dict[str, list[TodoItem]]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)

    def get(self, session_key: str) -> list[TodoItem]:
        """Return the todo list for the session."""
        if session_key in self._cache:
            return list(self._cache[session_key])
        data = self._load_all()
        out = data.get(session_key, [])
        self._cache[session_key] = out
        return list(out)

    def update(self, session_key: str, todos: list[TodoItem]) -> None:
        """Replace the todo list for the session."""
        normalized = [
            {
                "content": str(t.get("content", "")).strip(),
                "status": str(t.get("status", "pending")).strip() or "pending",
                "priority": str(t.get("priority", "medium")).strip() or "medium",
            }
            for t in todos
        ]
        self._cache[session_key] = normalized
        data = self._load_all()
        data[session_key] = normalized
        self._save_all(data)
