from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from .models import entities  # noqa: F401 — registers all ORM models
from .routers import auth, account, campaigns, contacts, drafts, templates, send
from .services.queue_worker import process_due_send_jobs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "static"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _worker_loop(stop_event: threading.Event) -> None:
    import time
    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                result = process_due_send_jobs(db, limit=50)
            if result.get("sent", 0) > 0:
                logger.info("Worker sent %d emails", result["sent"])
        except Exception:
            logger.exception("Worker loop error")
        stop_event.wait(30.0)


def create_app() -> FastAPI:
    app = FastAPI(title="Finance Recruiting Killer", version="1.0.0")

    # Session middleware (must be first)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup():
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")

        # Start background send worker
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_worker_loop, args=(stop_event,),
            name="send-worker", daemon=True
        )
        thread.start()
        app.state.worker_stop = stop_event
        logger.info("Background send worker started")

    @app.on_event("shutdown")
    def _shutdown():
        if hasattr(app.state, "worker_stop"):
            app.state.worker_stop.set()

    # ── Health ─────────────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # ── Include routers ────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(campaigns.router)
    app.include_router(contacts.router)
    app.include_router(drafts.router)
    app.include_router(templates.router)
    app.include_router(send.router)

    # ── Google OAuth callback (matches registered redirect URI) ────────────────
    # The registered URI is /auth/google/callback (not /api/auth/...)
    from fastapi.responses import RedirectResponse
    import requests as _requests

    @app.get("/auth/google/callback")
    def google_callback_root(request: Request):
        from .routers.auth import google_callback
        return google_callback(request, request.query_params.get("code"), request.query_params.get("error"))

    # ── Static files ──────────────────────────────────────────────────────────
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    # ── Page routes ───────────────────────────────────────────────────────────
    @app.get("/")
    def serve_landing():
        f = FRONTEND_DIR / "index.html"
        return FileResponse(f) if f.exists() else JSONResponse({"app": "Finance Recruiting Killer"})

    @app.get("/login")
    def serve_login():
        f = FRONTEND_DIR / "login.html"
        return FileResponse(f) if f.exists() else JSONResponse({"error": "login.html not found"})

    @app.get("/app")
    @app.get("/app/{rest:path}")
    def serve_app(rest: str = ""):
        f = FRONTEND_DIR / "app.html"
        return FileResponse(f) if f.exists() else JSONResponse({"error": "app.html not found"})

    return app


app = create_app()
