from __future__ import annotations

import base64
import html as html_mod
import json
import logging
import os
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


def _plain_to_html(body: str) -> str:
    """Convert plain-text body to HTML preserving paragraph spacing."""
    text = body.replace('\r\n', '\n').replace('\r', '\n')
    escaped = html_mod.escape(text)
    paragraphs = escaped.split('\n\n')
    parts = []
    for para in paragraphs:
        inner = para.replace('\n', '<br>')
        parts.append(f'<p style="margin:0 0 1em 0;line-height:1.5;">{inner}</p>')
    return (
        '<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#000;">'
        + ''.join(parts)
        + '</body></html>'
    )


def _build_mime_message(
    to_email: str,
    from_email: str,
    subject: str,
    body: str,
    resume_path: str | None = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["To"] = to_email
    msg["From"] = from_email
    msg["Subject"] = subject

    # multipart/alternative so clients pick the best version (HTML preferred)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "plain", "utf-8"))
    alt.attach(MIMEText(_plain_to_html(body), "html", "utf-8"))
    msg.attach(alt)

    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(resume_path).name)
        display_name = re.sub(r"^\d+_", "", Path(resume_path).name)
        part["Content-Disposition"] = f'attachment; filename="{display_name}"'
        msg.attach(part)

    return msg


def send_via_gmail(
    gmail_token_json: str,
    to_email: str,
    from_email: str,
    subject: str,
    body: str,
    resume_path: str | None = None,
    on_token_refresh: Any | None = None,
) -> bool:
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleRequest
        from googleapiclient.discovery import build

        token_data = json.loads(gmail_token_json)
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )

        # Proactively refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            if on_token_refresh:
                updated = {
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
                }
                on_token_refresh(json.dumps(updated))

        service = build("gmail", "v1", credentials=creds)
        msg = _build_mime_message(to_email, from_email, subject, body, resume_path)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info("Sent email to %s via Gmail API", to_email)
        return True

    except Exception as exc:
        logger.error("Gmail send error: %s", exc)
        return False


def simulate_send(
    to_email: str,
    subject: str,
    body: str,
    resume_path: str | None = None,
) -> bool:
    outbox = Path(settings.outbox_storage_path)
    outbox.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in to_email)
    eml_path = outbox / f"{safe}.eml"
    with open(eml_path, "w") as f:
        f.write(f"To: {to_email}\nSubject: {subject}\n\n{body}")
    logger.info("Simulated send to %s — saved to %s", to_email, eml_path)
    return True
