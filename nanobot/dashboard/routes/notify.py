"""Push notifications: SSE /api/events and POST /api/notify (for gateway cron delivery)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse as FastAPIStreamingResponse
from pydantic import BaseModel

from nanobot.dashboard.notify_store import add_queue, push, remove_queue
from nanobot.dashboard.store import get as get_user_by_token

router = APIRouter(prefix="/api", tags=["notify"])


class NotifyBody(BaseModel):
    user_id: str
    session_id: str = ""
    content: str = ""


async def get_user_id_for_sse(request: Request) -> str:
    """Resolve user_id from query param 'token' (EventSource cannot send Authorization header) or cookie."""
    token = request.query_params.get("token")
    if not token and request.cookies:
        token = request.cookies.get("nanobot_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = get_user_by_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user_id


@router.get("/events")
async def sse_events(
    request: Request,
    user_id: str = Depends(get_user_id_for_sse),
):
    """Server-Sent Events stream for push notifications (e.g. cron reminders)."""
    queue = add_queue(user_id)
    try:
        async def event_stream():
            try:
                while True:
                    try:
                        session_id, content = await asyncio.wait_for(queue.get(), timeout=30.0)
                        payload = json.dumps({"session_id": session_id, "content": content}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                remove_queue(user_id, queue)
        return FastAPIStreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        remove_queue(user_id, queue)
        raise


@router.post("/notify")
async def notify(body: NotifyBody):
    """Receive a notification (e.g. from gateway when a cron job runs for channel=dashboard). No auth; for internal use."""
    await push(body.user_id, body.session_id or "", body.content or "")
    return {"ok": True}
