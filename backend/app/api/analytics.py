"""Endpoint /api/analytics — registrazione manuale performance Instagram."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Analytics, Content

router = APIRouter()


class AnalyticsIn(BaseModel):
    impressions: Optional[int] = None
    reach: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    saves: Optional[int] = None
    shares: Optional[int] = None


@router.post("/{cid}")
def record(cid: int, payload: AnalyticsIn, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    a = Analytics(content_id=cid, **payload.model_dump(exclude_none=True))
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"ok": True, "analytics_id": a.id}


@router.get("/{cid}")
def history(cid: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Analytics).where(Analytics.content_id == cid).order_by(Analytics.measured_at)
    ).scalars().all()
    return [
        {
            "measured_at": r.measured_at,
            "impressions": r.impressions, "reach": r.reach,
            "likes": r.likes, "comments": r.comments,
            "saves": r.saves, "shares": r.shares,
        }
        for r in rows
    ]


@router.get("/top/engagement")
def top_engagement(limit: int = 10, db: Session = Depends(get_db)):
    """Top contenuti per engagement (likes+comments+saves)."""
    rows = db.execute(select(Analytics)).scalars().all()
    by_content: dict[int, dict] = {}
    for r in rows:
        agg = by_content.setdefault(r.content_id, {"likes": 0, "comments": 0, "saves": 0})
        agg["likes"] += r.likes or 0
        agg["comments"] += r.comments or 0
        agg["saves"] += r.saves or 0
    ranked = sorted(
        by_content.items(),
        key=lambda kv: kv[1]["likes"] + 2 * kv[1]["comments"] + 3 * kv[1]["saves"],
        reverse=True,
    )[:limit]
    out = []
    for cid, agg in ranked:
        c = db.get(Content, cid)
        if not c:
            continue
        out.append({
            "content_id": cid,
            "title": c.title,
            "kind": c.kind,
            "likes": agg["likes"], "comments": agg["comments"], "saves": agg["saves"],
        })
    return out
