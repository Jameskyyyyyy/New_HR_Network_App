from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..database import SessionLocal
from ..models.entities import Template

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/templates", tags=["templates"])


def _require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _serialize_template(t: Template) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "subject_template": t.subject_template,
        "body_template": t.body_template,
        "resume_path": t.resume_path,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class TemplateCreate(BaseModel):
    name: str
    subject_template: str = ""
    body_template: str = ""
    resume_path: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    resume_path: str | None = None


@router.get("")
def list_templates(request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        templates = db.query(Template).filter(Template.user_id == user_id).order_by(Template.created_at.desc()).all()
        return {"templates": [_serialize_template(t) for t in templates]}
    finally:
        db.close()


@router.get("/{template_id}")
def get_template(template_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        t = db.query(Template).filter(Template.id == template_id, Template.user_id == user_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        return _serialize_template(t)
    finally:
        db.close()


@router.post("")
def create_template(payload: TemplateCreate, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        t = Template(
            user_id=user_id,
            name=payload.name,
            subject_template=payload.subject_template,
            body_template=payload.body_template,
            resume_path=payload.resume_path,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return _serialize_template(t)
    finally:
        db.close()


@router.put("/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        t = db.query(Template).filter(Template.id == template_id, Template.user_id == user_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        if payload.name is not None:
            t.name = payload.name
        if payload.subject_template is not None:
            t.subject_template = payload.subject_template
        if payload.body_template is not None:
            t.body_template = payload.body_template
        if payload.resume_path is not None:
            t.resume_path = payload.resume_path
        db.commit()
        return _serialize_template(t)
    finally:
        db.close()


@router.delete("/{template_id}")
def delete_template(template_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        t = db.query(Template).filter(Template.id == template_id, Template.user_id == user_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        db.delete(t)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/{template_id}/duplicate")
def duplicate_template(template_id: int, request: Request):
    user_id = _require_user(request)
    db = SessionLocal()
    try:
        t = db.query(Template).filter(Template.id == template_id, Template.user_id == user_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        new_t = Template(
            user_id=user_id,
            name=f"{t.name} (Copy)",
            subject_template=t.subject_template,
            body_template=t.body_template,
            resume_path=t.resume_path,
        )
        db.add(new_t)
        db.commit()
        db.refresh(new_t)
        return _serialize_template(new_t)
    finally:
        db.close()
