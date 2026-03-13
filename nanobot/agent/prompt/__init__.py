"""Agent prompt assets (OpenCode-style). Load from nanobot/agent/prompt/*.txt."""

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str, fallback: str = "") -> str:
    """
    Load prompt text from nanobot/agent/prompt/<name>.txt.
    If the file is missing, return fallback (default empty string).
    """
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        return fallback
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return fallback
