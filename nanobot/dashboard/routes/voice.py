"""Voice: POST /api/voice/transcribe."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from nanobot.auth import get_user_root
from nanobot.config.loader import load_config
from nanobot.dashboard.deps import get_current_user_id
from nanobot.utils.helpers import ensure_dir

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(
    user_id: str = Depends(get_current_user_id),
    file: UploadFile = File(...),
):
    """Transcribe audio file to text (e.g. for voice input). Returns { \"text\": \"...\" }."""
    config = load_config()
    api_key = config.providers.groq.api_key if config.providers else None
    if not api_key:
        raise HTTPException(503, "Groq API key not configured for transcription")
    media_dir = ensure_dir(get_user_root(user_id) / "media")
    suffix = Path(file.filename or "audio").suffix or ".webm"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=media_dir) as tmp:
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = Path(tmp.name)
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        from nanobot.providers.transcription import GroqTranscriptionProvider
        provider = GroqTranscriptionProvider(api_key=api_key)
        text = await provider.transcribe(tmp_path)
        return {"text": text or ""}
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
