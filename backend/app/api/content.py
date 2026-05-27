"""Endpoint /api/content — list, get, update, approve/reject."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Content
from ..schemas import ApprovalAction, ContentDraft, ContentOut

router = APIRouter()


@router.get("", response_model=list[ContentOut])
def list_contents(
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    stmt = select(Content)
    if status:
        stmt = stmt.where(Content.status == status)
    if kind:
        stmt = stmt.where(Content.kind == kind)
    stmt = stmt.order_by(desc(Content.created_at)).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/{cid}", response_model=ContentOut)
def get_content(cid: int, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    return c


@router.put("/{cid}", response_model=ContentOut)
def update_content(cid: int, payload: ContentDraft, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    c.kind = payload.kind
    c.title = payload.title
    c.hook = payload.hook
    c.caption = payload.caption
    c.hashtags = payload.hashtags
    c.cta = payload.cta
    c.slides_json = [s.model_dump() for s in payload.slides] if payload.slides else None
    c.reel_script = payload.reel_script
    c.paper_id = payload.paper_id
    if payload.provider:
        c.provider = payload.provider
    c.status = "draft"  # modifica riapre la review
    db.commit()
    db.refresh(c)
    return c


@router.post("/{cid}/approve", response_model=ContentOut)
def approve_or_reject(cid: int, action: ApprovalAction, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    if action.action == "approve":
        # blocca se ci sono errori di validazione
        val = c.validation_json or {}
        if isinstance(val, dict) and val.get("ok") is False:
            raise HTTPException(400, "Non puoi approvare un contenuto con errori di validazione. Modifica o rigenera prima.")
        c.status = "approved"
    else:
        c.status = "rejected"
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{cid}")
def delete_content(cid: int, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/{cid}/publish")
def mark_published(cid: int, db: Session = Depends(get_db)):
    """Marca come pubblicato (pubblicazione manuale o futura integrazione Meta API)."""
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    if c.status not in ("approved", "scheduled"):
        raise HTTPException(400, "Solo contenuti approvati/programmati possono essere pubblicati.")
    c.status = "published"
    c.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
