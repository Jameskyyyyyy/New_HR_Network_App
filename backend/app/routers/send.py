from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..database import SessionLocal
from ..models.entities import Campaign, CampaignStatus, Draft, DraftStatus, SendJob, SendJobStatus
from ..services.scheduling import calculate_send_times

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/send", tags=["send"])


def _require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


class SendPayload(BaseModel):
    campaign_id: int
    allowed_days: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    window_start: str = "09:30 AM"
    window_end: str = "05:00 PM"
    daily_cap: int = 20
    hourly_cap: int = 15
    interval_min: int = 1
    interval_max: int = 15


@router.post("")
def queue_send(payload: SendPayload, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(
            Campaign.id == payload.campaign_id, Campaign.user_id == user_id
        ).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        approved_drafts = db.query(Draft).filter(
            Draft.campaign_id == payload.campaign_id,
            Draft.status == DraftStatus.approved,
        ).all()

        if not approved_drafts:
            raise HTTPException(status_code=400, detail="No approved drafts to send")

        send_times = calculate_send_times(
            count=len(approved_drafts),
            allowed_days=payload.allowed_days,
            window_start=payload.window_start,
            window_end=payload.window_end,
            daily_cap=payload.daily_cap,
            interval_min=payload.interval_min,
            interval_max=payload.interval_max,
        )

        jobs_created = 0
        for i, draft in enumerate(approved_drafts):
            scheduled_at = send_times[i] if i < len(send_times) else datetime.utcnow()
            job = SendJob(
                campaign_id=payload.campaign_id,
                draft_id=draft.id,
                scheduled_at=scheduled_at,
                status=SendJobStatus.queued,
            )
            db.add(job)
            jobs_created += 1

        campaign.status = CampaignStatus.sending
        db.commit()

        return {"queued": jobs_created, "campaign_id": payload.campaign_id}
    finally:
        db.close()
