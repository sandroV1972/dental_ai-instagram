"""Endpoint /api/schedule — calendario editoriale + export."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Content, ScheduleSlot
from ..schemas import ScheduleRequest

router = APIRouter()


@router.get("")
def list_slots(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    stmt = select(ScheduleSlot)
    if start:
        stmt = stmt.where(ScheduleSlot.slot_at >= start)
    if end:
        stmt = stmt.where(ScheduleSlot.slot_at <= end)
    stmt = stmt.order_by(ScheduleSlot.slot_at)
    slots = db.execute(stmt).scalars().all()
    out = []
    for s in slots:
        c = db.get(Content, s.content_id)
        out.append({
            "slot_id": s.id,
            "content_id": s.content_id,
            "slot_at": s.slot_at,
            "channel": s.channel,
            "notes": s.notes,
            "content_title": c.title if c else None,
            "content_kind": c.kind if c else None,
            "content_status": c.status if c else None,
        })
    return out


@router.post("/{cid}")
def schedule_content(cid: int, req: ScheduleRequest, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    if c.status not in ("approved", "scheduled"):
        raise HTTPException(400, "Solo contenuti approvati possono essere programmati.")
    slot = ScheduleSlot(content_id=cid, slot_at=req.slot_at, channel=req.channel, notes=req.notes)
    db.add(slot)
    c.status = "scheduled"
    c.scheduled_at = req.slot_at
    db.commit()
    db.refresh(slot)
    return {"slot_id": slot.id, "ok": True}


@router.delete("/{slot_id}")
def remove_slot(slot_id: int, db: Session = Depends(get_db)):
    s = db.get(ScheduleSlot, slot_id)
    if not s:
        raise HTTPException(404, "Slot non trovato")
    cid = s.content_id
    db.delete(s)
    # se non ci sono piu' slot, rimetti il content come approved
    remaining = db.execute(select(ScheduleSlot).where(ScheduleSlot.content_id == cid)).first()
    if not remaining:
        c = db.get(Content, cid)
        if c and c.status == "scheduled":
            c.status = "approved"
            c.scheduled_at = None
    db.commit()
    return {"ok": True}


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    """Export CSV per Buffer/Later/Hootsuite (date, channel, title, caption, hashtags)."""
    slots = db.execute(select(ScheduleSlot).order_by(ScheduleSlot.slot_at)).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scheduled_at", "channel", "title", "caption", "hashtags", "kind", "notes"])
    for s in slots:
        c = db.get(Content, s.content_id)
        if not c:
            continue
        writer.writerow([
            s.slot_at.isoformat() if s.slot_at else "",
            s.channel,
            c.title,
            c.caption,
            c.hashtags,
            c.kind,
            s.notes or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=schedule.csv"},
    )
