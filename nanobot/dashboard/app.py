"""FastAPI application for nanobot dashboard."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from nanobot.auth import allowed_users_path
from nanobot.dashboard.routes import (
    auth_router,
    chat_router,
    notify_router,
    sessions_router,
    upload_router,
    voice_router,
)


def _static_dir(config_allowed_users_path: str | None) -> Path | None:
    """Resolve dashboard static root: CONSOLE_STATIC_DIR > project root console/dist > cwd/console/dist."""
    env_dir = os.environ.get("CONSOLE_STATIC_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        if p.is_dir():
            return p
    # Project root: nanobot/dashboard/app.py -> parent.parent = nanobot pkg, parent.parent.parent = repo root
    try:
        root = Path(__file__).resolve().parent.parent.parent
        for name in ("console/dist", "console_dist"):
            p = root / name
            if p.is_dir():
                return p
    except Exception:
        pass
    cwd = Path.cwd()
    for name in ("console/dist", "console_dist"):
        p = cwd / name
        if p.is_dir():
            return p
    return None


def _lifespan_with_gateway():
    """Lifespan: start cron services for all users when --with-gateway; stop on shutdown."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.dashboard.agent_runner import run_agent_for_user
    from nanobot.dashboard.notify_store import push

    cron_services: list[CronService] = []
    global_cron_path = (get_data_dir() / "cron" / "jobs.json").resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nanobot_root = Path.home() / ".nanobot"
        if nanobot_root.is_dir():
            for user_dir in nanobot_root.iterdir():
                if not user_dir.is_dir() or user_dir.name.startswith("."):
                    continue
                jobs_file = user_dir / "cron" / "jobs.json"
                if not jobs_file.is_file():
                    continue
                resolved_jobs = jobs_file.resolve()
                if resolved_jobs == global_cron_path:
                    continue
                uid = user_dir.name
                cron = CronService(resolved_jobs)

                async def on_job_cb(job: CronJob):
                    try:
                        response = await run_agent_for_user(
                            uid,
                            job.payload.message,
                            session_key=f"cron:{job.id}",
                            channel=job.payload.channel or "dashboard",
                            chat_id=job.payload.to or uid,
                        )
                        content = response or job.payload.message
                    except Exception:
                        content = job.payload.message
                    if job.payload.deliver and job.payload.to and job.payload.channel == "dashboard":
                        sid = job.payload.to.split(":", 1)[1] if ":" in job.payload.to else ""
                        await push(uid, sid, content or "")
                    return content

                cron.on_job = on_job_cb
                await cron.start()
                cron_services.append(cron)
        yield
        for c in cron_services:
            c.stop()

    return lifespan


def create_app(
    auth_path: Path | None = None,
    config_allowed_users_path: str | None = None,
    with_gateway: bool = False,
) -> FastAPI:
    lifespan = _lifespan_with_gateway() if with_gateway else None
    app = FastAPI(title="Nanobot Dashboard", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.auth_path = auth_path or allowed_users_path(config_allowed_users_path)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(notify_router)
    app.include_router(sessions_router)
    app.include_router(upload_router)
    app.include_router(voice_router)

    static_root = _static_dir(config_allowed_users_path)
    if static_root:
        index_path = static_root / "index.html"
        assets = static_root / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            fp = static_root / full_path
            if fp.is_file():
                return FileResponse(str(fp))
            if index_path.exists():
                return FileResponse(str(index_path))
            raise HTTPException(status_code=404, detail="Not found")
    else:
        # Placeholder: minimal HTML so dashboard command runs without frontend build
        _placeholder_html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Nanobot Dashboard</title></head>
<body style="font-family:system-ui;padding:2rem;background:#0f172a;color:#e2e8f0;">
<h1>Nanobot Dashboard</h1>
<p>Frontend not found. From repo root run: <code>cd console && npm run build</code></p>
<p>Or set env <code>CONSOLE_STATIC_DIR</code> to the path of <code>console/dist</code>.</p>
<p>Login API: <code>POST /api/auth/login</code> (JSON body: user_id, password)</p>
</body></html>"""

        @app.get("/")
        async def index():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(_placeholder_html)

    return app
