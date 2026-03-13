"""Todo tools: todowrite and todoread (OpenCode-style)."""

from typing import Any, TYPE_CHECKING

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.session.todo import TodoStore


class TodoWriteTool(Tool):
    """Update the session todo list."""

    def __init__(self, store: "TodoStore"):
        self._store = store
        self._session_key: str = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "todowrite"

    @property
    def description(self) -> str:
        return (
            "Update the todo list for this conversation. "
            "Provide a list of items with content, status (pending, in_progress, completed, cancelled), and priority (high, medium, low). "
            "Use this to track and split work."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Brief description"},
                            "status": {
                                "type": "string",
                                "description": "pending | in_progress | completed | cancelled",
                            },
                            "priority": {
                                "type": "string",
                                "description": "high | medium | low",
                            },
                        },
                        "required": ["content", "status", "priority"],
                    },
                    "description": "The updated todo list",
                },
            },
            "required": ["todos"],
        }

    async def execute(self, todos: list[dict[str, Any]], **kwargs: Any) -> str:
        self._store.update(self._session_key, todos)
        pending = sum(1 for t in todos if t.get("status") != "completed")
        return f"{pending} todo(s) remaining.\n" + "\n".join(
            f"[{'x' if t.get('status') == 'completed' else ' '}] {t.get('content', '')}"
            for t in todos
        )


class TodoReadTool(Tool):
    """Read the session todo list."""

    def __init__(self, store: "TodoStore"):
        self._store = store
        self._session_key: str = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "todoread"

    @property
    def description(self) -> str:
        return "Read the current todo list for this conversation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        todos = self._store.get(self._session_key)
        if not todos:
            return "No todos."
        return "\n".join(
            f"[{'x' if t.get('status') == 'completed' else ' '}] {t.get('content', '')} ({t.get('priority', 'medium')})"
            for t in todos
        )
