from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models.entities import Draft, DraftStatus, SendJob, SendJobStatus, User
from .sender import send_via_gmail, simulate_send

logger = logging.getLogger(__name__)


def process_due_send_jobs(db: Session, limit: int = 50) -> dict[str, Any]:
    now = datetime.utcnow()
    jobs = (
        db.query(SendJob)
        .filter(SendJob.status == SendJobStatus.queued, SendJob.scheduled_at <= now)
        .limit(limit)
        .all()
    )

    sent = 0
    failed = 0

    for job in jobs:
        draft: Draft | None = db.query(Draft).filter(Draft.id == job.draft_id).first()
        if not draft:
            job.status = SendJobStatus.failed
            job.last_error = "Draft not found"
            failed += 1
            continue

        contact = draft.contact
        campaign = draft.campaign
        user: User | None = db.query(User).filter(User.id == campaign.user_id).first() if campaign else None

        to_email = contact.email if contact else None
        if not to_email:
            job.status = SendJobStatus.failed
            job.last_error = "No email address for contact"
            failed += 1
            continue

        job.attempts = (job.attempts or 0) + 1

        try:
            if settings.simulate_email_send or not (user and user.gmail_token_json):
                success = simulate_send(
                    to_email=to_email,
                    subject=draft.subject or "",
                    body=draft.body or "",
                    resume_path=draft.resume_path,
                )
            else:
                from_email = user.gmail_email or user.email
                success = send_via_gmail(
                    gmail_token_json=user.gmail_token_json,
                    to_email=to_email,
                    from_email=from_email,
                    subject=draft.subject or "",
                    body=draft.body or "",
                    resume_path=draft.resume_path,
                )

            if success:
                job.status = SendJobStatus.sent
                job.sent_at = datetime.utcnow()
                draft.status = DraftStatus.sent
                draft.sent_at = datetime.utcnow()
                sent += 1
            else:
                job.status = SendJobStatus.failed
                job.last_error = "Send returned False"
                failed += 1

        except Exception as exc:
            job.status = SendJobStatus.failed
            job.last_error = str(exc)
            failed += 1
            logger.exception("Error processing job %s", job.id)

    db.commit()
    return {"sent": sent, "failed": failed, "total": len(jobs)}
