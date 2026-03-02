from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.entities import Campaign, Contact
from ..services.contact_generation import JobContextLike, generate_contacts

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

        # Build structured inputs for the search engine
        companies = [c.strip() for c in payload.company_list.split(",") if c.strip()]
        cities = [c.strip() for c in payload.location_list.split(",") if c.strip()]
        schools = [s.strip() for s in payload.target_schools.split(",") if s.strip()]
        levels = [l.strip() for l in payload.seniority_levels.split(",") if l.strip()] or ["Analyst", "Associate"]
        keywords = [k.strip() for k in payload.title_keywords.split(",") if k.strip()]

        n_companies = max(1, len(companies))
        # Divide total target evenly across companies (minimum 1 per company)
        max_per_company = max(1, payload.target_count // n_companies)
        # Give a small surplus so we can trim to exact target after dedup
        gather_target_per_company = max_per_company + 2

        filters = {
            "companies": companies,
            "selected_cities": cities,
            "selected_schools": schools,
            "seniority_levels": levels,
            "custom_keywords": keywords,
            "front_office_keywords": [],
            "hr_keywords": [],
            "max_per_company": gather_target_per_company,
        }

        job_context = JobContextLike(
            job_name=payload.name,
            company=companies[0] if companies else "",
            city=cities[0] if cities else "New York",
            extracted_keywords=keywords,
        )

        # Run the search
        result = generate_contacts(filters, job_context, settings.serpapi_key)
        raw_contacts = result.rows

        # Filter duplicates
        if payload.avoid_duplicates:
            raw_contacts = [c for c in raw_contacts if c.get("email") not in previously_sent]

        # Trim to exact target count
        raw_contacts = raw_contacts[:payload.target_count]

        # Save to DB
        saved: list[Contact] = []
        for c in raw_contacts:
            raw_data = c.get("raw_data") or {}
            ct = Contact(
                campaign_id=campaign.id,
                first_name=c.get("first_name"),
                last_name=c.get("last_name"),
                title=c.get("title"),
                company=c.get("company"),
                location=c.get("city"),      # old app uses "city", DB model uses "location"
                school=c.get("school"),
                linkedin_url=c.get("linkedin_url"),
                email=c.get("email"),
                fit_score=float(raw_data.get("fit_score") or 0),
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
