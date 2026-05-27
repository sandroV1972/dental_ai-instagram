"""Endpoint /api/generation — genera un draft a partire da prompt e/o paper.

- POST /api/generation       genera il solo TESTO (compat con UX precedente)
- POST /api/generation/full  genera testo + render immagini + (opz.) video in una sola call
                              [usato dal nuovo flusso semplificato della dashboard]
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Content, Paper
from ..schemas import ContentOut, GenerationRequest
from ..services.ai import AIProviderError, available_providers
from ..services.generation import generate_content
from ..services.validation import validate_content_rules

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/providers")
def providers():
    return {"available": available_providers()}


@router.post("", response_model=ContentOut)
def generate(req: GenerationRequest, db: Session = Depends(get_db)):
    paper: Paper | None = None
    if req.paper_id:
        paper = db.get(Paper, req.paper_id)
        if not paper:
            raise HTTPException(404, "Paper non trovato")

    if not paper and not (req.prompt and req.prompt.strip()):
        raise HTTPException(400, "Servono almeno paper_id o prompt.")

    try:
        gen = generate_content(
            kind=req.kind,
            provider_name=req.provider,
            free_prompt=req.prompt,
            paper_title=paper.title if paper else None,
            paper_abstract=paper.abstract if paper else None,
            paper_journal=paper.journal if paper else None,
            paper_authors=paper.authors if paper else None,
            paper_doi=paper.doi if paper else None,
            paper_pmid=paper.pmid if paper else None,
            technical_level=req.technical_level,
            target_slides=req.target_slides,
            extra_instructions=req.extra_instructions,
        )
    except AIProviderError as e:
        raise HTTPException(502, f"AI provider error: {e}")

    val = validate_content_rules(
        kind=req.kind,
        title=gen.title,
        caption=gen.caption,
        hashtags=gen.hashtags,
        slides=gen.slides,
        reel_script=gen.reel_script,
    )

    content = Content(
        paper_id=paper.id if paper else None,
        kind=req.kind,
        title=gen.title or "Senza titolo",
        hook=gen.hook,
        caption=gen.caption,
        hashtags=gen.hashtags,
        cta=gen.cta,
        slides_json=gen.slides or None,
        reel_script=gen.reel_script,
        provider=gen.provider,
        model=gen.model,
        prompt=gen.raw_prompt,
        validation_json=val.as_dict(),
        status="draft" if val.ok else "draft",  # comunque draft, ma flaggato
    )
    db.add(content)
    if paper:
        paper.status = "used"
    db.commit()
    db.refresh(content)
    return content


# --- Endpoint unificato per UX semplificata ---

class FullGenerationRequest(GenerationRequest):
    """Estende GenerationRequest con i parametri per il render delle immagini."""
    image_source: Optional[str] = None  # ai | wikimedia | unsplash | none
    build_video: bool = False           # solo per kind="reel"


@router.post("/full")
def generate_full(req: FullGenerationRequest, db: Session = Depends(get_db)):
    """One-shot endpoint: genera testo + valida + renderizza immagini + (opz.) video.

    Restituisce un payload arricchito:
      {
        "content": ContentOut,
        "images": ["/renders/.../slide_01.png", ...],
        "attributions": [...],
        "video": "/renders/.../reel.mp4" | null
      }
    """
    # 1) Genera il TESTO (logica identica a /api/generation senza response_model)
    paper: Paper | None = None
    if req.paper_id:
        paper = db.get(Paper, req.paper_id)
        if not paper:
            raise HTTPException(404, "Paper non trovato")
    if not paper and not (req.prompt and req.prompt.strip()):
        raise HTTPException(400, "Servono almeno paper_id o prompt.")

    try:
        gen = generate_content(
            kind=req.kind,
            provider_name=req.provider,
            free_prompt=req.prompt,
            paper_title=paper.title if paper else None,
            paper_abstract=paper.abstract if paper else None,
            paper_journal=paper.journal if paper else None,
            paper_authors=paper.authors if paper else None,
            paper_doi=paper.doi if paper else None,
            paper_pmid=paper.pmid if paper else None,
            technical_level=req.technical_level,
            target_slides=req.target_slides,
            extra_instructions=req.extra_instructions,
        )
    except AIProviderError as e:
        raise HTTPException(502, f"AI provider error: {e}")

    val = validate_content_rules(
        kind=req.kind, title=gen.title, caption=gen.caption,
        hashtags=gen.hashtags, slides=gen.slides, reel_script=gen.reel_script,
    )

    content = Content(
        paper_id=paper.id if paper else None,
        kind=req.kind,
        title=gen.title or "Senza titolo",
        hook=gen.hook, caption=gen.caption, hashtags=gen.hashtags,
        cta=gen.cta, slides_json=gen.slides or None, reel_script=gen.reel_script,
        provider=gen.provider, model=gen.model, prompt=gen.raw_prompt,
        validation_json=val.as_dict(), status="draft",
    )
    db.add(content)
    if paper:
        paper.status = "used"
    db.commit()
    db.refresh(content)

    # 2) Renderizza le immagini chiamando direttamente la logica del render endpoint
    # (import lazy per evitare cicli)
    from .render import render_content as _do_render, render_video as _do_render_video

    try:
        render_resp = _do_render(content.id, db=db, image_source=req.image_source)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("Render fallito per content %d: %s", content.id, e)
        render_resp = {"images": [], "attributions": [], "source": req.image_source or "none"}

    # 3) Se è un reel e l'utente lo chiede, costruisci anche il video
    video_url = None
    if req.kind == "reel" and req.build_video:
        try:
            v = _do_render_video(content.id, db=db)
            video_url = v.get("video")
        except HTTPException as e:
            logger.warning("Video build skipped: %s", e.detail)
        except Exception as e:  # noqa: BLE001
            logger.exception("Video build crash: %s", e)

    # Re-fetch per la versione aggiornata (status non cambia ma per coerenza)
    db.refresh(content)
    return {
        "content": ContentOut.model_validate(content).model_dump(mode="json"),
        "images": render_resp.get("images", []),
        "attributions": render_resp.get("attributions", []),
        "image_source": render_resp.get("source"),
        "video": video_url,
    }
