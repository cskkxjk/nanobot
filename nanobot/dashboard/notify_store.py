"""In-memory store for dashboard push notifications (per-user queues for SSE)."""

from __future__ import annotations

import asyncio
from typing import Any

# user_id -> list of asyncio.Queue; each queue gets (session_id, content) tuples
_user_queues: dict[str, list[asyncio.Queue[tuple[str, str]]]] = {}


def add_queue(user_id: str) -> asyncio.Queue[tuple[str, str]]:
    """Add a new queue for this user (e.g. new SSE connection). Returns the queue."""
    q: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    if user_id not in _user_queues:
        _user_queues[user_id] = []
    _user_queues[user_id].append(q)
    return q


def remove_queue(user_id: str, queue: asyncio.Queue[tuple[str, str]]) -> None:
    """Remove a queue when the client disconnects."""
    if user_id not in _user_queues:
        return
    try:
        _user_queues[user_id].remove(queue)
    except ValueError:
        pass
    if not _user_queues[user_id]:
        del _user_queues[user_id]


async def push(user_id: str, session_id: str, content: str) -> None:
    """Push a notification to all connected clients for this user."""
    if user_id not in _user_queues:
        return
    for q in list(_user_queues[user_id]):
        try:
            q.put_nowait((session_id, content))
        except asyncio.QueueFull:
            pass
