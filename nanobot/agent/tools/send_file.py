"""Tool to send a file to the user (via current channel)."""

from pathlib import Path
from typing import Any, Awaitable, Callable

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.filesystem import _resolve_path
from nanobot.bus.events import OutboundMessage


class SendFileTool(Tool):
    """Send a file to the user on the current channel. Requires set_context(channel, chat_id) to be set by the agent loop."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
    ):
        self._send_callback = send_callback
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._channel = ""
        self._chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "send_file"

    @property
    def description(self) -> str:
        return "Send a file to the user on the current chat channel. Use after generating or reading a file the user asked for. Path is relative to workspace or absolute."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to send"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        if not self._channel or not self._chat_id:
            return "Error: No target channel/chat set. send_file is only available when processing a user message."
        if not self._send_callback:
            return "Error: Send callback not configured."
        try:
            resolved = _resolve_path(path, self._workspace, self._allowed_dir)
        except PermissionError as e:
            return f"Error: {e}"
        if not resolved.exists():
            return f"Error: File not found: {path}"
        if not resolved.is_file():
            return f"Error: Not a file: {path}"
        msg = OutboundMessage(
            channel=self._channel,
            chat_id=self._chat_id,
            content=f"File: {resolved.name}",
            media=[str(resolved.resolve())],
        )
        try:
            await self._send_callback(msg)
            return f"Sent file to user: {resolved.name}"
        except Exception as e:
            return f"Error sending file: {e}"
