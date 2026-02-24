from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    scheduled = "scheduled"
    sending = "sending"
    ended = "ended"


class DraftStatus(str, enum.Enum):
    generated = "generated"
    approved = "approved"
    sent = "sent"
    failed = "failed"


class SendJobStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    gmail_token_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gmail_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="user")
    templates: Mapped[list["Template"]] = relationship("Template", back_populates="user")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    company_list: Mapped[str] = mapped_column(Text, default="")
    title_keywords: Mapped[str] = mapped_column(Text, default="")
    location_list: Mapped[str] = mapped_column(Text, default="")
    target_schools: Mapped[str] = mapped_column(Text, default="")
    seniority_levels: Mapped[str] = mapped_column(String(255), default="Analyst,Associate")
    target_count: Mapped[int] = mapped_column(Integer, default=10)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), default=CampaignStatus.draft
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="campaigns")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="campaign")
    drafts: Mapped[list["Draft"]] = relationship("Draft", back_populates="campaign")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="contacts")
    drafts: Mapped[list["Draft"]] = relationship("Draft", back_populates="contact")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id"), nullable=False)

    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus), default=DraftStatus.generated
    )
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("templates.id"), nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="drafts")
    contact: Mapped["Contact"] = relationship("Contact", back_populates="drafts")
    template: Mapped["Template | None"] = relationship("Template")
    send_jobs: Mapped[list["SendJob"]] = relationship("SendJob", back_populates="draft")


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_template: Mapped[str] = mapped_column(Text, default="")
    body_template: Mapped[Text] = mapped_column(Text, default="")
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="templates")


class SendJob(Base):
    __tablename__ = "send_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("drafts.id"), nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[SendJobStatus] = mapped_column(
        Enum(SendJobStatus), default=SendJobStatus.queued
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    draft: Mapped["Draft"] = relationship("Draft", back_populates="send_jobs")
