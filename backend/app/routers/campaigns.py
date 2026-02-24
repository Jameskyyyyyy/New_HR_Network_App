from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.entities import Campaign, CampaignStatus, Contact, Draft, DraftStatus, SendJob, SendJobStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _serialize_campaign(c: Campaign) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "company_list": c.company_list,
        "title_keywords": c.title_keywords,
        "location_list": c.location_list,
        "target_schools": c.target_schools,
        "seniority_levels": c.seniority_levels,
        "target_count": c.target_count,
        "status": c.status.value if c.status else "draft",
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


class CampaignCreate(BaseModel):
    name: str
    company_list: str = ""
    title_keywords: str = ""
    location_list: str = ""
    target_schools: str = ""
    seniority_levels: str = "Analyst,Associate"
    target_count: int = 10


class CampaignUpdate(BaseModel):
    name: str | None = None
    company_list: str | None = None
    title_keywords: str | None = None
    location_list: str | None = None
    target_schools: str | None = None
    seniority_levels: str | None = None
    target_count: int | None = None
    status: str | None = None


@router.get("")
def list_campaigns(request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).order_by(Campaign.created_at.desc()).all()
        result = []
        for c in campaigns:
            d = _serialize_campaign(c)
            # Add contact/draft counts
            d["contact_count"] = db.query(Contact).filter(Contact.campaign_id == c.id).count()
            d["selected_count"] = db.query(Contact).filter(Contact.campaign_id == c.id, Contact.selected == True).count()
            d["sent_count"] = db.query(Draft).filter(Draft.campaign_id == c.id, Draft.status == DraftStatus.sent).count()
            d["approved_count"] = db.query(Draft).filter(Draft.campaign_id == c.id, Draft.status == DraftStatus.approved).count()
            result.append(d)
        return {"campaigns": result}
    finally:
        db.close()


@router.get("/stats")
def campaign_stats(request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        campaign_ids = [c.id for c in db.query(Campaign).filter(Campaign.user_id == user_id).all()]
        total_campaigns = len(campaign_ids)

        if not campaign_ids:
            return {
                "campaigns": 0,
                "contacts_selected": 0,
                "approved": 0,
                "sent": 0,
                "queued": 0,
                "avg_fit_score": 0,
                "chart_data": [],
            }

        selected = db.query(Contact).filter(Contact.campaign_id.in_(campaign_ids), Contact.selected == True).count()
        approved = db.query(Draft).filter(Draft.campaign_id.in_(campaign_ids), Draft.status == DraftStatus.approved).count()
        sent = db.query(Draft).filter(Draft.campaign_id.in_(campaign_ids), Draft.status == DraftStatus.sent).count()
        queued = db.query(SendJob).filter(SendJob.campaign_id.in_(campaign_ids), SendJob.status == SendJobStatus.queued).count()

        avg_fit_row = db.query(func.avg(Contact.fit_score)).filter(
            Contact.campaign_id.in_(campaign_ids), Contact.selected == True
        ).scalar()
        avg_fit = round(float(avg_fit_row or 0), 1)

        # Build chart data (last 30 days, sent by day)
        from datetime import datetime, timedelta
        chart_data = []
        today = datetime.utcnow().date()
        for i in range(29, -1, -1):
            day = today - timedelta(days=i)
            sent_jobs = db.query(SendJob).filter(
                SendJob.campaign_id.in_(campaign_ids),
                SendJob.status == SendJobStatus.sent,
                func.date(SendJob.sent_at) == day,
            ).count()
            chart_data.append({"date": day.isoformat(), "sent": sent_jobs})

        return {
            "campaigns": total_campaigns,
            "contacts_selected": selected,
            "approved": approved,
            "sent": sent,
            "queued": queued,
            "avg_fit_score": avg_fit,
            "chart_data": chart_data,
        }
    finally:
        db.close()


@router.get("/{campaign_id}")
def get_campaign(campaign_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        d = _serialize_campaign(c)
        d["contacts"] = [
            {
                "id": ct.id,
                "first_name": ct.first_name,
                "last_name": ct.last_name,
                "title": ct.title,
                "company": ct.company,
                "location": ct.location,
                "school": ct.school,
                "linkedin_url": ct.linkedin_url,
                "email": ct.email,
                "fit_score": ct.fit_score,
                "selected": ct.selected,
            }
            for ct in c.contacts
        ]
        return d
    finally:
        db.close()


@router.post("")
def create_campaign(payload: CampaignCreate, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = Campaign(
            user_id=user_id,
            name=payload.name,
            company_list=payload.company_list,
            title_keywords=payload.title_keywords,
            location_list=payload.location_list,
            target_schools=payload.target_schools,
            seniority_levels=payload.seniority_levels,
            target_count=payload.target_count,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return {"id": c.id, "campaign": _serialize_campaign(c)}
    finally:
        db.close()


@router.put("/{campaign_id}")
def update_campaign(campaign_id: int, payload: CampaignUpdate, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if payload.name is not None:
            c.name = payload.name
        if payload.company_list is not None:
            c.company_list = payload.company_list
        if payload.title_keywords is not None:
            c.title_keywords = payload.title_keywords
        if payload.location_list is not None:
            c.location_list = payload.location_list
        if payload.target_schools is not None:
            c.target_schools = payload.target_schools
        if payload.seniority_levels is not None:
            c.seniority_levels = payload.seniority_levels
        if payload.target_count is not None:
            c.target_count = payload.target_count
        if payload.status is not None:
            try:
                c.status = CampaignStatus(payload.status)
            except ValueError:
                pass
        db.commit()
        return _serialize_campaign(c)
    finally:
        db.close()


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        db.delete(c)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/{campaign_id}/contacts/select")
def select_contacts(campaign_id: int, request: Request, payload: dict):
    user_id = _require_user(request)
    contact_ids: list[int] = payload.get("contact_ids", [])
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        # Deselect all first
        for ct in c.contacts:
            ct.selected = ct.id in contact_ids
        db.commit()
        return {"ok": True, "selected": len(contact_ids)}
    finally:
        db.close()


@router.get("/{campaign_id}/contacts/export")
def export_contacts_csv(campaign_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["First Name", "Last Name", "Title", "Company", "Location", "School", "LinkedIn", "Email", "Fit Score", "Selected"])
        for ct in c.contacts:
            writer.writerow([
                ct.first_name, ct.last_name, ct.title, ct.company,
                ct.location, ct.school, ct.linkedin_url, ct.email,
                ct.fit_score, ct.selected,
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=contacts_{campaign_id}.csv"},
        )
    finally:
        db.close()
