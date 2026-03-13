"""Dashboard API routes."""

from nanobot.dashboard.routes.auth import router as auth_router
from nanobot.dashboard.routes.chat import router as chat_router
from nanobot.dashboard.routes.notify import router as notify_router
from nanobot.dashboard.routes.sessions import router as sessions_router
from nanobot.dashboard.routes.upload import router as upload_router
from nanobot.dashboard.routes.voice import router as voice_router

__all__ = ["auth_router", "chat_router", "notify_router", "sessions_router", "upload_router", "voice_router"]
