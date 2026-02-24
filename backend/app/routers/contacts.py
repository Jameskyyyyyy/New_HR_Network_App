from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.entities import Campaign, Contact
from ..services.contact_generation import generate_contacts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def _require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


class GenerateContactsPayload(BaseModel):
    campaign_id: int | None = None
    name: str = "Untitled Campaign"
    company_list: str = ""
    title_keywords: str = ""
    location_list: str = ""
    target_schools: str = ""
    seniority_levels: str = "Analyst,Associate"
    target_count: int = 10
    regenerate: bool = False
    avoid_duplicates: bool = True


def _serialize_contact(ct: Contact) -> dict[str, Any]:
    return {
        "id": ct.id,
        "campaign_id": ct.campaign_id,
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


@router.post("/generate")
def generate(payload: GenerateContactsPayload, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        # Create or update campaign
        if payload.campaign_id:
            campaign = db.query(Campaign).filter(
                Campaign.id == payload.campaign_id, Campaign.user_id == user_id
            ).first()
            if not campaign:
                raise HTTPException(status_code=404, detail="Campaign not found")
            campaign.company_list = payload.company_list
            campaign.title_keywords = payload.title_keywords
            campaign.location_list = payload.location_list
            campaign.target_schools = payload.target_schools
            campaign.seniority_levels = payload.seniority_levels
            campaign.target_count = payload.target_count
            if payload.regenerate:
                db.query(Contact).filter(Contact.campaign_id == campaign.id).delete()
        else:
            campaign = Campaign(
                user_id=user_id,
                name=payload.name,
                company_list=payload.company_list,
                title_keywords=payload.title_keywords,
                location_list=payload.location_list,
                target_schools=payload.target_schools,
                seniority_levels=payload.seniority_levels,
                target_count=payload.target_count,
            )
            db.add(campaign)
            db.flush()

        db.commit()
        db.refresh(campaign)

        # Get previously sent emails for deduplication
        previously_sent: set[str] = set()
        if payload.avoid_duplicates:
            from ..models.entities import Draft, DraftStatus
            sent_drafts = (
                db.query(Draft)
                .join(Campaign)
                .filter(Campaign.user_id == user_id, Draft.status == DraftStatus.sent)
                .all()
            )
            previously_sent = {d.contact.email for d in sent_drafts if d.contact and d.contact.email}

        # Call generation service
        raw_contacts = generate_contacts(
            company_list=payload.company_list,
            title_keywords=payload.title_keywords,
            location_list=payload.location_list,
            target_schools=payload.target_schools,
            seniority_levels=payload.seniority_levels,
            target_count=payload.target_count,
        )

        # Filter duplicates
        if payload.avoid_duplicates:
            raw_contacts = [c for c in raw_contacts if c.get("email") not in previously_sent]

        # Save to DB
        saved: list[Contact] = []
        for c in raw_contacts:
            ct = Contact(
                campaign_id=campaign.id,
                first_name=c.get("first_name"),
                last_name=c.get("last_name"),
                title=c.get("title"),
                company=c.get("company"),
                location=c.get("location"),
                school=c.get("school"),
                linkedin_url=c.get("linkedin_url"),
                email=c.get("email"),
                fit_score=c.get("fit_score", 0.0),
            )
            db.add(ct)
            saved.append(ct)

        db.commit()
        for ct in saved:
            db.refresh(ct)

        return {
            "campaign_id": campaign.id,
            "contacts": [_serialize_contact(ct) for ct in saved],
        }
    finally:
        db.close()
