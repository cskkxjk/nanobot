"""Tool that returns the current local time with timezone info."""

from datetime import datetime, timezone
from typing import Any

from nanobot.agent.tools.base import Tool


class GetCurrentTimeTool(Tool):
    """Return the current system time with timezone information."""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return (
            "Get the current system time with timezone information. "
            "Returns local time in human-readable format including timezone name and UTC offset. "
            "Useful for time-sensitive tasks such as scheduling."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            now = datetime.now().astimezone()
            return now.strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
        except Exception:
            return datetime.now(timezone.utc).isoformat() + " (UTC)"
