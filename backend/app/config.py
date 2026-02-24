from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

STORAGE_ROOT = PROJECT_ROOT / "storage"
RESUME_STORAGE = STORAGE_ROOT / "resumes"
OUTBOX_STORAGE = STORAGE_ROOT / "outbox"

STORAGE_ROOT.mkdir(exist_ok=True)
RESUME_STORAGE.mkdir(exist_ok=True)
OUTBOX_STORAGE.mkdir(exist_ok=True)


class Settings:
    app_name: str = "Finance Recruiting Killer"
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/app.db")

    serpapi_key: str = os.getenv("SERPAPI_KEY", "")
    hunter_api_key: str = os.getenv("HUNTER_API_KEY", "")

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/auth/google/callback")

    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-please-change")

    resume_storage_path: str = str(RESUME_STORAGE)
    outbox_storage_path: str = str(OUTBOX_STORAGE)

    simulate_email_send: bool = os.getenv("SIMULATE_EMAIL_SEND", "false").lower() in {"1", "true", "yes"}


settings = Settings()
