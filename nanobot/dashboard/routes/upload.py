"""File upload: POST /api/upload; GET /api/upload/serve for reading back (e.g. session history images)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from nanobot.auth import get_user_root
from nanobot.dashboard.deps import get_current_user_id
from nanobot.utils.helpers import ensure_dir, safe_filename

router = APIRouter(prefix="/api/upload", tags=["upload"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".csv", ".md",
}


@router.post("")
async def upload_files(
    user_id: str = Depends(get_current_user_id),
    files: list[UploadFile] = File(...),
):
    """Upload files to user media dir; returns list of paths for use in chat."""
    media_dir = ensure_dir(get_user_root(user_id) / "media")
    paths = []
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type not allowed: {ext}")
        size = 0
        chunk_size = 1024 * 1024
        safe_name = safe_filename(f.filename) or "file"
        stem = Path(safe_name).stem[:50]
        out_name = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
        out_path = media_dir / out_name
        try:
            with open(out_path, "wb") as out:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        out_path.unlink(missing_ok=True)
                        raise HTTPException(400, f"File too large: {f.filename}")
                    out.write(chunk)
                    paths.append(str(out_path))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
    return {"paths": paths}


@router.get("/serve")
async def serve_uploaded_file(
    path: str,
    user_id: str = Depends(get_current_user_id),
):
    """Serve an uploaded file by path relative to user root (e.g. media/xxx.jpg). For session history images."""
    if not path or path.startswith("/") or ".." in path:
        raise HTTPException(400, "Invalid path")
    user_root = get_user_root(user_id).resolve()
    resolved = (user_root / path).resolve()
    try:
        resolved.relative_to(user_root)
    except ValueError:
        raise HTTPException(404, "File not found")
    if not resolved.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(resolved)
