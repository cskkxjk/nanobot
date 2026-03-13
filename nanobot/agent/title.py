"""Generate session title from first user message (OpenCode-style)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.prompt import load_prompt

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


async def generate_session_title(
    provider: LLMProvider,
    model: str,
    first_user_content: str,
    first_assistant_content: str | None = None,
    *,
    max_tokens: int = 80,
    temperature: float = 0.5,
) -> str | None:
    """
    Generate a short session title from the first conversation (user + optional assistant).
    Uses prompt from nanobot/agent/prompt/title.txt; no tools.
    Returns None on missing prompt, empty content, or provider error.
    """
    prompt = load_prompt("title")
    if not prompt:
        return None
    first_user_content = (first_user_content or "").strip()
    if not first_user_content:
        return None
    if first_assistant_content and (first_assistant_content or "").strip():
        content = f"User: {first_user_content}\nAssistant: {(first_assistant_content or '').strip()}"
    else:
        content = first_user_content
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": content},
    ]
    try:
        response = await provider.chat(
            messages=messages,
            tools=None,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = (response.content or "").strip()
        if not content:
            return None
        return content[:50]
    except Exception as e:
        logger.warning("Session title generation failed: {}", e)
        return None
