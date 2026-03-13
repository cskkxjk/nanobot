"""FastAPI dependencies for dashboard (auth)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyCookie

from nanobot.dashboard.store import get as get_user_by_token

_security_bearer = HTTPBearer(auto_error=False)
_cookie_scheme = APIKeyCookie(name="nanobot_token", auto_error=False)


async def get_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_security_bearer),
    cookie: str | None = Depends(_cookie_scheme),
) -> str | None:
    if creds and creds.scheme == "Bearer" and creds.credentials:
        return creds.credentials
    return cookie


async def get_current_user_id(token: str | None = Depends(get_token)) -> str:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user_id = get_user_by_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user_id
