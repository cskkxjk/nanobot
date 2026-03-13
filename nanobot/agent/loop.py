"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

# Type for optional tool-summary callback: (tool_name, status, title?, description?, output?) -> None
ToolSummaryCallback = Callable[
    [str, str, str | None, str | None, str | None],
    Awaitable[None],
]
# Type for optional thinking/reasoning callback
ThinkingCallback = Callable[[str], Awaitable[None]]
# Type for optional stream-delta callback (event_type, content)
StreamDeltaCallback = Callable[[str, str], Awaitable[None]]

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryConsolidator
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.title import generate_session_title
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.memory_search import MemorySearchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.search import GlobSearchTool, GrepSearchTool
from nanobot.agent.tools.send_file import SendFileTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.task import TaskTool
from nanobot.agent.tools.time import GetCurrentTimeTool
from nanobot.agent.tools.todo import TodoReadTool, TodoWriteTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.session.todo import TodoStore
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, ExecToolConfig, WebSearchConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 16_000
    _CONSECUTIVE_TOOL_ERROR_MAX = 3

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig, WebSearchConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self._todo_store = TodoStore(workspace)
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
        )
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(GrepSearchTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(GlobSearchTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(GetCurrentTimeTool())
        self.tools.register(MemorySearchTool(workspace=self.workspace))
        self.tools.register(SendFileTool(send_callback=self.bus.publish_outbound, workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(config=self.web_search_config, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "send_file", "spawn", "cron", "task", "todowrite", "todoread"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _tool_summary_title(tool_name: str, arguments: dict[str, Any]) -> tuple[str, str | None]:
        """Build a short title and optional description for CLI tool summary (OpenCode-style)."""
        args = arguments or {}
        # Prefer key order: path, command, query, url, etc.
        path = args.get("path") or args.get("file_path")
        cmd = args.get("command")
        query = args.get("query")
        url = args.get("url")
        name = args.get("name")
        if tool_name == "read_file" and path:
            return f"Read {path}", None
        if tool_name == "write_file" and path:
            return f"Write {path}", None
        if tool_name == "edit_file" and path:
            return f"Edit {path}", None
        if tool_name == "list_dir":
            return f"List {path or '.'}", None
        if tool_name == "exec" and cmd:
            short = cmd.strip()[:60] + "…" if len(cmd.strip()) > 60 else cmd.strip()
            return short, None
        if tool_name == "web_search" and query:
            return f'Web Search "{query[:50]}…"' if len(query) > 50 else f'Web Search "{query}"', None
        if tool_name == "web_fetch" and url:
            return f"WebFetch {url[:50]}…" if len(url) > 50 else f"WebFetch {url}", None
        if tool_name == "message":
            return "Message", None
        if tool_name == "spawn":
            return name or "Spawn", None
        if tool_name == "task":
            desc = args.get("description") or "Task"
            return desc, None
        if tool_name == "todowrite":
            return "Todos", None
        if tool_name == "todoread":
            return "Read todos", None
        if tool_name.startswith("mcp_"):
            return tool_name.replace("mcp_", "", 1).replace("_", " ").title(), None
        return tool_name.replace("_", " ").title(), None

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_tool_summary: ToolSummaryCallback | None = None,
        on_thinking: ThinkingCallback | None = None,
        on_stream_delta: StreamDeltaCallback | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        consecutive_tool_errors = 0
        tool_defs = self.tools.get_definitions()

        while iteration < self.max_iterations:
            iteration += 1

            tool_defs = self.tools.get_definitions()

            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=tool_defs,
                model=self.model,
            )

            if response.has_tool_calls:
                if on_thinking and response.reasoning_content and response.reasoning_content.strip():
                    await on_thinking(response.reasoning_content.strip())
                if on_progress:
                    thought = self._strip_think(response.content)
                    if thought:
                        await on_progress(thought)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    tc.to_openai_tool_call()
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    title, description = self._tool_summary_title(tool_call.name, tool_call.arguments)
                    if on_tool_summary:
                        await on_tool_summary(tool_call.name, "running", title, description, None)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    is_error = isinstance(result, str) and (
                        result.startswith("Error") or "(no output)" in result or "no output" in result.lower()
                    )
                    if is_error:
                        consecutive_tool_errors += 1
                    else:
                        consecutive_tool_errors = 0
                    status = "error" if is_error else "completed"
                    if on_tool_summary:
                        await on_tool_summary(tool_call.name, status, title, description, result)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                if consecutive_tool_errors >= self._CONSECUTIVE_TOOL_ERROR_MAX:
                    logger.info(
                        "Stopping after {} consecutive tool errors",
                        consecutive_tool_errors,
                    )
                    final_content = (
                        "I tried several approaches but couldn't complete your request "
                        "(the service may be unavailable or the tools didn't return useful data). "
                        "Please try again later or use another method (e.g. check the weather on your phone or in a browser)."
                    )
                    break
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    # #region agent log (debug)
                    try:
                        import json as _json
                        import time as _time
                        with open(
                            "/home/xujunkai/workspace/llm/nanobot/.cursor/debug-d43886.log",
                            "a",
                            encoding="utf-8",
                        ) as _f:
                            _f.write(
                                _json.dumps(
                                    {
                                        "sessionId": "d43886",
                                        "hypothesisId": "H_llm_error",
                                        "location": "nanobot/agent/loop.py:_run_agent_loop",
                                        "message": "LLM returned finish_reason=error",
                                        "data": {
                                            "content": (response.content or "")[:500],
                                            "contentFullLen": len(response.content or ""),
                                            "iteration": iteration,
                                        },
                                        "timestamp": int(_time.time() * 1000),
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                    except Exception:
                        pass
                    # #endregion agent log (debug)
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            cmd = msg.content.strip().lower()
            if cmd == "/stop":
                await self._handle_stop(msg)
            elif cmd == "/restart":
                await self._handle_restart(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _handle_restart(self, msg: InboundMessage) -> None:
        """Restart the process in-place via os.execv."""
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        ))

        async def _do_restart():
            await asyncio.sleep(1)
            # Use -m nanobot instead of sys.argv[0] for Windows compatibility
            # (sys.argv[0] may be just "nanobot" without full path on Windows)
            os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

        asyncio.create_task(_do_restart())

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        *,
        sse_on_thinking: ThinkingCallback | None = None,
        sse_on_stream_delta: StreamDeltaCallback | None = None,
        sse_on_tool_summary: ToolSummaryCallback | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=0)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            title_set = self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            try:
                if not await self.memory_consolidator.archive_unconsolidated(session):
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Memory archival failed, session not cleared. Please try again.",
                    )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            lines = [
                "🐈 nanobot commands:",
                "/new — Start a new conversation",
                "/stop — Stop the current task",
                "/restart — Restart the bot",
                "/help — Show available commands",
            ]
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines),
            )
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=0)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        async def _on_tool_summary(
            tool_name: str,
            status: str,
            title: str | None,
            description: str | None,
            output: str | None,
        ) -> None:
            meta: dict[str, Any] = {
                "type": "tool_summary",
                "tool_name": tool_name,
                "status": status,
                "title": title,
                "description": description,
                "output": output,
            }
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=output or "",
                metadata=meta,
            ))
            if sse_on_tool_summary:
                await sse_on_tool_summary(tool_name, status, title, description, output)

        async def _on_thinking(text: str) -> None:
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=text,
                metadata={"type": "reasoning"},
            ))
            if sse_on_thinking:
                await sse_on_thinking(text)

        async def _on_stream_delta(event_type: str, content: str) -> None:
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
                metadata={"type": event_type},
            ))
            if sse_on_stream_delta:
                await sse_on_stream_delta(event_type, content)

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
            on_tool_summary=_on_tool_summary,
            on_thinking=_on_thinking if msg.channel in ("cli", "dashboard") else None,
            on_stream_delta=_on_stream_delta if msg.channel in ("cli", "dashboard") else None,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        title_set = self._save_turn(session, all_msgs, 1 + len(history), user_media_paths=msg.media or [])
        self.sessions.save(session)
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(
        self,
        session: Session,
        messages: list[dict],
        skip: int,
        *,
        user_media_paths: list[str] | None = None,
    ) -> bool:
        """Save new-turn messages into session, truncating large tool results.
        Returns True if we set a temporary title from the first user message (caller may run LLM title generation).
        """
        from datetime import datetime

        _image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        user_root = self.workspace.parent

        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    # Strip the runtime-context prefix, keep only the user text.
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = []
                    for c in content:
                        if c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                            continue  # Strip runtime context from multimodal messages
                        if (c.get("type") == "image_url"
                                and c.get("image_url", {}).get("url", "").startswith("data:image/")):
                            filtered.append({"type": "text", "text": "[image]"})
                        else:
                            filtered.append(c)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()
        title_set_from_first = False
        if not session.metadata.get("title"):
            for m in session.messages:
                if m.get("role") == "user":
                    raw = m.get("content")
                    title = ""
                    if isinstance(raw, str):
                        title = raw.replace("\n", " ").strip()[:50]
                    elif isinstance(raw, list):
                        for part in raw:
                            if isinstance(part, dict) and part.get("type") == "text":
                                title = (part.get("text") or "").replace("\n", " ").strip()[:50]
                                break
                    if title:
                        session.metadata["title"] = title
                        title_set_from_first = True
                    break
        return title_set_from_first

    def _first_user_content(self, session: Session) -> str:
        """Extract first user message content as plain text for title generation."""
        for m in session.messages:
            if m.get("role") != "user":
                continue
            raw = m.get("content")
            if isinstance(raw, str):
                return raw.replace("\n", " ").strip()
            if isinstance(raw, list):
                for part in raw:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return (part.get("text") or "").replace("\n", " ").strip()
            return ""
        return ""

    def _first_assistant_content(self, session: Session) -> str:
        """Extract first assistant message content as plain text for title generation."""
        for m in session.messages:
            if m.get("role") != "assistant":
                continue
            raw = m.get("content")
            if isinstance(raw, str):
                return raw.replace("\n", " ").strip()
            if isinstance(raw, list):
                for part in raw:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return (part.get("text") or "").replace("\n", " ").strip()
            return ""
        return ""

    async def _maybe_generate_title(self, session: Session) -> None:
        """Generate session title via LLM from first conversation and update session; keep current title on failure."""
        user_content = self._first_user_content(session)
        if not user_content:
            return
        assistant_content = self._first_assistant_content(session)
        title = await generate_session_title(
            self.provider,
            self.model,
            user_content,
            first_assistant_content=assistant_content or None,
        )
        if title:
            session.metadata["title"] = title
            self.sessions.save(session)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""
