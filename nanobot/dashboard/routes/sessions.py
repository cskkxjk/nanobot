"""Session list and create: GET/POST /api/sessions; GET session messages."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from nanobot.auth import get_user_root
from nanobot.dashboard.deps import get_current_user_id
from nanobot.session.manager import SessionManager
from nanobot.utils.helpers import ensure_dir

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _message_content_to_text(content: Any) -> str:
    """Extract plain text from a stored message content (string or list of parts)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            t = (part.get("text") or "").strip()
            if t and t != "[image]":
                parts.append(t)
    return "\n\n".join(parts) if parts else ""


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return message history for the given session (user + assistant only) for display."""
    workspace = get_user_root(user_id) / "workspace"
    if not workspace.is_dir():
        return {"messages": []}
    sm = SessionManager(workspace)
    key = f"dashboard:{user_id}:{session_id}"
    session = sm.get_or_create(key)
    out: list[dict[str, Any]] = []
    for m in session.messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        raw = m.get("content")
        text = _message_content_to_text(raw)
        item: dict[str, Any] = {"role": role, "content": text}
        if "attachment_paths" in m and m["attachment_paths"]:
            item["attachment_paths"] = m["attachment_paths"]
        out.append(item)
    return {"messages": out}


@router.get("")
async def list_sessions(user_id: str = Depends(get_current_user_id)):
    """List current user's dashboard sessions."""
    workspace = get_user_root(user_id) / "workspace"
    if not workspace.is_dir():
        return []
    sm = SessionManager(workspace)
    prefix = f"dashboard:{user_id}:"
    items = []
    for s in sm.list_sessions():
        key = s.get("key") or ""
        if not key.startswith(prefix):
            continue
        session_id = key[len(prefix):] if len(key) > len(prefix) else key
        items.append({
            "key": key,
            "session_id": session_id,
            "title": s.get("title") or "New chat",
            "updated_at": s.get("updated_at"),
            "created_at": s.get("created_at"),
        })
    return items


@router.post("")
async def create_session(user_id: str = Depends(get_current_user_id)):
    """Create a new session; returns session_id for use in chat."""
    ensure_dir(get_user_root(user_id) / "workspace")
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}
