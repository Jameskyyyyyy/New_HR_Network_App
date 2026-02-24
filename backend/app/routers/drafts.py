from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.entities import Campaign, Contact, Draft, DraftStatus, Template
from ..services.drafting import generate_draft, DEFAULT_SUBJECT, DEFAULT_BODY

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drafts"])


def _require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _serialize_draft(d: Draft) -> dict[str, Any]:
    contact = d.contact
    return {
        "id": d.id,
        "campaign_id": d.campaign_id,
        "contact_id": d.contact_id,
        "subject": d.subject,
        "body": d.body,
        "status": d.status.value if d.status else "generated",
        "resume_path": d.resume_path,
        "template_id": d.template_id,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "contact": {
            "id": contact.id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "title": contact.title,
            "company": contact.company,
            "email": contact.email,
            "linkedin_url": contact.linkedin_url,
            "fit_score": contact.fit_score,
        } if contact else None,
    }


class DraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None


class DraftsGeneratePayload(BaseModel):
    template_id: int | None = None
    resume_path: str | None = None


@router.get("/api/campaigns/{campaign_id}/drafts")
def list_drafts(campaign_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        drafts = db.query(Draft).filter(Draft.campaign_id == campaign_id).all()
        return {"drafts": [_serialize_draft(d) for d in drafts]}
    finally:
        db.close()


@router.post("/api/campaigns/{campaign_id}/drafts/generate")
def generate_drafts(campaign_id: int, payload: DraftsGeneratePayload, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")

        selected_contacts = db.query(Contact).filter(
            Contact.campaign_id == campaign_id, Contact.selected == True
        ).all()

        if not selected_contacts:
            raise HTTPException(status_code=400, detail="No contacts selected")

        # Get template
        subject_tpl = DEFAULT_SUBJECT
        body_tpl = DEFAULT_BODY
        resume_path = payload.resume_path

        if payload.template_id:
            tmpl = db.query(Template).filter(Template.id == payload.template_id).first()
            if tmpl:
                subject_tpl = tmpl.subject_template or DEFAULT_SUBJECT
                body_tpl = tmpl.body_template or DEFAULT_BODY
                if not resume_path and tmpl.resume_path:
                    resume_path = tmpl.resume_path

        drafts_created: list[Draft] = []
        for ct in selected_contacts:
            # Check if draft already exists
            existing = db.query(Draft).filter(
                Draft.campaign_id == campaign_id, Draft.contact_id == ct.id
            ).first()

            contact_data = {
                "first_name": ct.first_name or "",
                "last_name": ct.last_name or "",
                "title": ct.title or "",
                "company": ct.company or "",
                "location": ct.location or "",
                "school": ct.school or "",
            }
            subject, body = generate_draft(subject_tpl, body_tpl, contact_data)

            if existing:
                existing.subject = subject
                existing.body = body
                existing.template_id = payload.template_id
                existing.resume_path = resume_path
                existing.status = DraftStatus.generated
                drafts_created.append(existing)
            else:
                d = Draft(
                    campaign_id=campaign_id,
                    contact_id=ct.id,
                    subject=subject,
                    body=body,
                    status=DraftStatus.generated,
                    template_id=payload.template_id,
                    resume_path=resume_path,
                )
                db.add(d)
                drafts_created.append(d)

        db.commit()
        for d in drafts_created:
            db.refresh(d)

        return {"drafts": [_serialize_draft(d) for d in drafts_created]}
    finally:
        db.close()


@router.patch("/api/drafts/{draft_id}")
def patch_draft(draft_id: int, payload: DraftPatch, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        d = db.query(Draft).filter(Draft.id == draft_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found")
        if payload.subject is not None:
            d.subject = payload.subject
        if payload.body is not None:
            d.body = payload.body
        db.commit()
        db.refresh(d)
        return _serialize_draft(d)
    finally:
        db.close()


@router.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, request: Request, payload: dict = {}):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        d = db.query(Draft).filter(Draft.id == draft_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found")
        approved = payload.get("approved", True)
        d.status = DraftStatus.approved if approved else DraftStatus.generated
        db.commit()
        return {"id": d.id, "status": d.status.value}
    finally:
        db.close()


@router.post("/api/drafts/{draft_id}/test")
def send_test(draft_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        from ..models.entities import User
        d = db.query(Draft).filter(Draft.id == draft_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        from ..services.sender import send_via_gmail, simulate_send
        if user.gmail_token_json and not settings.simulate_email_send:
            success = send_via_gmail(
                gmail_token_json=user.gmail_token_json,
                to_email=user.email,
                from_email=user.gmail_email or user.email,
                subject=f"[TEST] {d.subject}",
                body=d.body or "",
                resume_path=d.resume_path,
            )
        else:
            success = simulate_send(
                to_email=user.email,
                subject=f"[TEST] {d.subject}",
                body=d.body or "",
                resume_path=d.resume_path,
            )
        return {"ok": success, "sent_to": user.email}
    finally:
        db.close()


@router.post("/api/campaigns/{campaign_id}/resume")
async def upload_resume(campaign_id: int, request: Request, file: UploadFile = File(...)):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")

        import aiofiles
        safe_name = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in (file.filename or "resume.pdf"))
        save_path = os.path.join(settings.resume_storage_path, f"{campaign_id}_{safe_name}")

        async with aiofiles.open(save_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        return {"ok": True, "resume_path": save_path, "filename": safe_name, "size": len(content)}
    finally:
        db.close()
