"""Run the agent for a given user (used by cron callbacks when dashboard runs with --with-gateway)."""

from __future__ import annotations

from nanobot.auth import ensure_user_workspace, get_user_root
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.loader import load_config, make_provider
from nanobot.cron.service import CronService
from nanobot.session.manager import SessionManager
from nanobot.agent.loop import AgentLoop


async def run_agent_for_user(
    user_id: str,
    message: str,
    session_key: str,
    *,
    channel: str = "dashboard",
    chat_id: str | None = None,
) -> str:
    """Create an agent for the given user, run one message, return the response text."""
    uid = (user_id or "").strip()
    if not uid:
        return ""
    ensure_user_workspace(uid, silent=True)
    config = load_config()
    try:
        provider = make_provider(config)
    except ValueError:
        return ""
    workspace = get_user_root(uid) / "workspace"
    session_manager = SessionManager(workspace)
    cron_store_path = (get_user_root(uid) / "cron" / "jobs.json").resolve()
    cron_service = CronService(cron_store_path)
    bus = MessageBus()
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron_service,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )
    try:
        await agent._connect_mcp()
        msg = InboundMessage(
            channel=channel,
            sender_id=uid,
            chat_id=chat_id or uid,
            content=message,
            media=[],
        )
        response = await agent._process_message(msg, session_key=session_key)
        return response.content if response else ""
    finally:
        await agent.close_mcp()
