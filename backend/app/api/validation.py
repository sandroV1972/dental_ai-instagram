"""Endpoint /api/validation — ricontrolla contenuti e verifica fonti."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Content, Source
from ..services.validation import validate_content_rules, verify_source, verify_sources_in_text

router = APIRouter()


@router.post("/{cid}")
def revalidate_content(cid: int, db: Session = Depends(get_db)):
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    slides = c.slides_json if isinstance(c.slides_json, list) else []
    val = validate_content_rules(
        kind=c.kind, title=c.title, caption=c.caption, hashtags=c.hashtags,
        slides=slides, reel_script=c.reel_script,
    )

    # Verifica fonti dichiarate nel testo
    text_blob = " ".join(filter(None, [c.title, c.caption, c.hashtags, c.reel_script or ""]))
    for s in slides:
        text_blob += " " + " ".join(filter(None, [(s or {}).get("title"), (s or {}).get("body")]))
    source_results = verify_sources_in_text(text_blob)

    # Aggiorna tabella sources
    for r in source_results:
        existing = next((s for s in c.sources if s.kind == r.kind and s.identifier == r.identifier), None)
        if not existing:
            existing = Source(content_id=c.id, kind=r.kind, identifier=r.identifier)
            c.sources.append(existing)
        existing.verified = r.verified
        existing.title = r.title
        existing.verification_message = r.message
        existing.checked_at = datetime.now(timezone.utc)

    # Aggiungi issue se qualche fonte non e' verificata
    payload = val.as_dict()
    payload["sources_checked"] = [
        {"kind": r.kind, "identifier": r.identifier, "verified": r.verified,
         "title": r.title, "message": r.message}
        for r in source_results
    ]
    invalid = [r for r in source_results if not r.verified]
    if invalid:
        payload["ok"] = False
        for r in invalid:
            payload["issues"].append({
                "code": "source_not_verified",
                "severity": "error",
                "message": f"Fonte {r.kind.upper()} {r.identifier} non verificata: {r.message}",
                "field": "caption",
            })

    c.validation_json = payload
    db.commit()
    return payload


@router.post("/source/check")
def check_source(kind: str, identifier: str):
    if kind.lower() not in {"doi", "pmid"}:
        raise HTTPException(400, "Kind deve essere 'doi' o 'pmid'.")
    res = verify_source(kind, identifier)
    return {
        "kind": res.kind, "identifier": res.identifier,
        "verified": res.verified, "title": res.title, "message": res.message,
    }
