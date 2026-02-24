from __future__ import annotations

import json
import logging
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.entities import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_db() -> Session:
    return SessionLocal()


@router.get("/google/login")
def google_login(request: Request) -> RedirectResponse:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/google/callback")
def google_callback(request: Request, code: str | None = None, error: str | None = None):
    if error or not code:
        return RedirectResponse("/login?error=oauth_denied")

    # Exchange code for tokens
    token_resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        logger.error("Token exchange failed: %s", token_resp.text)
        return RedirectResponse("/login?error=token_exchange_failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")

    # Get user info
    userinfo_resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if userinfo_resp.status_code != 200:
        return RedirectResponse("/login?error=userinfo_failed")

    userinfo = userinfo_resp.json()
    email = userinfo.get("email")
    if not email:
        return RedirectResponse("/login?error=no_email")

    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email)
            db.add(user)
            db.flush()

        user.gmail_email = email
        user.gmail_token_json = json.dumps(token_data)
        from datetime import datetime
        user.gmail_connected_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        request.session["user_id"] = user.id
        request.session["user_email"] = user.email

    finally:
        db.close()

    return RedirectResponse("/app")


@router.get("/me")
def get_me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {
            "id": user.id,
            "email": user.email,
            "gmail_connected": bool(user.gmail_token_json),
            "gmail_email": user.gmail_email,
        }
    finally:
        db.close()


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}
