"""Auth routes: login, logout."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from nanobot.auth import (
    allowed_users_path,
    validate_user,
    ensure_user_workspace,
)
from nanobot.dashboard.store import delete, put
from nanobot.dashboard.deps import get_current_user_id, get_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    user_id: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody, request: Request):
    auth_path: Path = getattr(request.app.state, "auth_path", None)
    if auth_path is None:
        auth_path = allowed_users_path(None)
    return await _login_impl(body, auth_path)


async def _login_impl(body: LoginBody, auth_path: Path) -> LoginResponse:
    if not auth_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured (allowed_users file missing)",
        )
    user_id = (body.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
    ok, _ = validate_user(user_id, body.password, auth_path)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user_id or password")
    ensure_user_workspace(user_id)
    token = str(uuid.uuid4())
    put(token, user_id)
    return LoginResponse(token=token, user_id=user_id)


@router.post("/logout")
async def logout(token: str | None = Depends(get_token)):
    if token:
        delete(token)
    return {"ok": True}


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}
