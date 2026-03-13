"""In-memory session store for dashboard auth (no persistence)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

# token -> (user_id, created_at)
_sessions: dict[str, tuple[str, datetime]] = {}


def put(token: str, user_id: str) -> None:
    _sessions[token] = (user_id, datetime.now())


def get(token: str) -> str | None:
    if not token:
        return None
    entry = _sessions.get(token)
    if not entry:
        return None
    return entry[0]


def delete(token: str) -> None:
    _sessions.pop(token, None)
