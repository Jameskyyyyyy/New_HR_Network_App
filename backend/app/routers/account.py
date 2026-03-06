from __future__ import annotations

import json
import logging
from datetime import datetime
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..database import SessionLocal
from ..models.entities import Campaign, Contact, Draft, DraftStatus, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/account", tags=["account"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_user(request: Request) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()


@router.get("")
def get_account(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        connected_at = user.gmail_connected_at.isoformat() if user.gmail_connected_at else None
        return {
            "email": user.email,
            "gmail_connected": bool(user.gmail_token_json),
            "gmail_email": user.gmail_email,
            "gmail_connected_at": connected_at,
        }
    finally:
        db.close()


FREE_CAMPAIGN_LIMIT = 3
FREE_CONTACT_LIMIT = 15


@router.get("/usage")
def get_usage(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        plan = (user.plan or "free")
        is_free = plan == "free"
        campaign_ids = [c.id for c in db.query(Campaign).filter(Campaign.user_id == user_id).all()]
        campaigns_used = len(campaign_ids)
        contacts_used = db.query(Contact).filter(Contact.campaign_id.in_(campaign_ids)).count() if campaign_ids else 0
        emails_sent = db.query(Draft).filter(Draft.campaign_id.in_(campaign_ids), Draft.status == DraftStatus.sent).count() if campaign_ids else 0
        return {
            "plan": plan,
            "campaigns_used": campaigns_used,
            "campaigns_limit": FREE_CAMPAIGN_LIMIT if is_free else None,
            "contacts_used": contacts_used,
            "contacts_limit": FREE_CONTACT_LIMIT if is_free else None,
            "emails_sent": emails_sent,
        }
    finally:
        db.close()


@router.post("/plan")
def set_plan(request: Request, payload: dict):
    """Dev/test endpoint to toggle between free and pro plans."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    plan = payload.get("plan", "free")
    if plan not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="Invalid plan")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.plan = plan
        db.commit()
        return {"plan": plan}
    finally:
        db.close()


@router.post("/gmail/connect")
def connect_gmail(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from ..routers.auth import SCOPES
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(user_id),
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"url": url}


@router.post("/gmail/disconnect")
def disconnect_gmail(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.gmail_token_json = None
            user.gmail_email = None
            user.gmail_connected_at = None
            db.commit()
        return {"ok": True}
    finally:
        db.close()
