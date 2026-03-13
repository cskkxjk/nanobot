"""Task tool: run a subagent to completion and return result (OpenCode-style)."""

from typing import Any, TYPE_CHECKING

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class TaskTool(Tool):
    """Run a subagent to complete a task and return the result (no background spawn)."""

    def __init__(self, subagent_manager: "SubagentManager"):
        self._subagents = subagent_manager
        self._session_key: str = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set session context for task_id naming (optional)."""
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return (
            "Run a dedicated subagent to complete a single task and return its result. "
            "Use for multi-step or focused subtasks (e.g. research, code review). "
            "The subagent runs to completion; you get task_id and the result text. "
            "Optionally pass task_id to resume a previous task session."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short (3–5 word) description of the task",
                },
                "prompt": {
                    "type": "string",
                    "description": "Full instructions for the subagent",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional: resume a previous task by id",
                },
            },
            "required": ["description", "prompt"],
        }

    async def execute(
        self,
        description: str,
        prompt: str,
        task_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        task_id_out, result = await self._subagents.run_task_blocking(
            description=description,
            prompt=prompt,
            task_id=task_id,
        )
        return (
            f"task_id: {task_id_out} (for resuming if needed)\n\n"
            f"<task_result>\n{result}\n</task_result>"
        )
