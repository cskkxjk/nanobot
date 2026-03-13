"""Chat route: POST /api/chat/send with SSE stream."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.responses import StreamingResponse as StarletteStreamingResponse


class SSEStreamingResponse(StarletteStreamingResponse):
    """StreamingResponse that only runs stream_response(), avoiding task-group cancel of listen_for_disconnect which logs CancelledError when stream ends normally."""

    async def __call__(self, scope, receive, send):
        try:
            await self.stream_response(send)
        except OSError:
            from starlette.responses import ClientDisconnect
            raise ClientDisconnect()
        except asyncio.CancelledError:
            pass
        if getattr(self, "background", None) is not None:
            await self.background()

from nanobot.auth import ensure_user_workspace, get_user_root
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.loader import load_config, make_provider
from nanobot.cron.service import CronService
from nanobot.session.manager import SessionManager
from nanobot.agent.loop import AgentLoop
from nanobot.dashboard.deps import get_current_user_id

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatBody(BaseModel):
    message: str
    session_id: str | None = None
    media_urls: list[str] | None = None


def _sse_event(event: str, data: str | dict) -> str:
    """Encode data as JSON so multi-line strings are sent in one SSE data field."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/send")
async def chat_send(
    body: ChatBody,
    user_id: str = Depends(get_current_user_id),
):
    """Send a message and stream the response as SSE."""
    session_id = body.session_id or str(uuid.uuid4())
    media_urls = body.media_urls or []
    uid = (user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_id required")
    config = load_config()
    try:
        provider = make_provider(config)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    ensure_user_workspace(uid, silent=True)
    workspace = get_user_root(uid) / "workspace"
    session_manager = SessionManager(workspace)
    cron_store_path = (get_user_root(uid) / "cron" / "jobs.json").resolve()
    from nanobot.config.loader import get_data_dir
    if cron_store_path == (get_data_dir() / "cron" / "jobs.json").resolve():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cron path resolved to global store; use per-user path")
    cron_service = CronService(cron_store_path)
    bus = MessageBus()
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron_service,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )
    await agent._connect_mcp()
    session_key = f"dashboard:{uid}:{session_id}"
    msg = InboundMessage(
        channel="dashboard",
        sender_id=uid,
        chat_id=f"{uid}:{session_id}",
        content=body.message,
        media=media_urls,
    )
    queue: asyncio.Queue[tuple[str, str | dict] | None] = asyncio.Queue()

    async def sse_on_thinking(text: str) -> None:
        await queue.put(("reasoning", text))

    async def sse_on_stream_delta(event_type: str, content: str) -> None:
        await queue.put((event_type, content))

    async def sse_on_tool_summary(
        tool_name: str,
        status: str,
        title: str | None,
        description: str | None,
        output: str | None,
    ) -> None:
        await queue.put((
            "tool_summary",
            {
                "tool_name": tool_name,
                "status": status,
                "title": title,
                "description": description,
                "output": output,
            },
        ))

    async def on_progress(content: str, *, tool_hint: bool = False) -> None:
        await queue.put(("tool_hint" if tool_hint else "progress", content))

    async def run_agent() -> None:
        try:
            response = await agent._process_message(
                msg,
                session_key=session_key,
                on_progress=on_progress,
                sse_on_thinking=sse_on_thinking,
                sse_on_stream_delta=sse_on_stream_delta,
                sse_on_tool_summary=sse_on_tool_summary,
            )
            final = response.content if response else ""
            user_root = get_user_root(uid)
            attachment_paths: list[str] = []
            while bus.outbound_size > 0:
                try:
                    out = await asyncio.wait_for(bus.consume_outbound(), timeout=0.5)
                except asyncio.TimeoutError:
                    break
                if out.media:
                    for p in out.media:
                        try:
                            resolved = Path(p).resolve()
                            rel = resolved.relative_to(user_root.resolve())
                            attachment_paths.append(str(rel))
                        except (ValueError, OSError):
                            pass
            if attachment_paths:
                await queue.put(("message", {"text": final, "attachment_paths": attachment_paths}))
            else:
                await queue.put(("message", final))
        except Exception as e:
            await queue.put(("error", str(e)))
        finally:
            await queue.put(None)
            await agent.close_mcp()

    async def event_stream():
        task = asyncio.create_task(run_agent())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                ev, data = item
                yield _sse_event(ev, data)
        finally:
            await task

    return SSEStreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
