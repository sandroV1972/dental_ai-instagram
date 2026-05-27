"""Endpoint a supporto del wizard step-by-step (stile predis.ai).

- POST /api/wizard/variants    genera N varianti immagine senza creare un Content
- POST /api/wizard/finalize    salva canvas finali (PNG base64) + testo come Content
- GET  /api/wizard/imagecheck  diagnostica: config caricata + lista modelli disponibili
"""
from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Content
from ..schemas import ContentOut
from ..services.imagegen import (
    GeminiImageProvider, ImageGenError, ImagenProvider, PollinationsProvider,
)
from ..services.imagesearch import UnsplashSearch, WikimediaSearch
from ..services.validation import validate_content_rules

logger = logging.getLogger(__name__)
router = APIRouter()

RENDERS_DIR = Path("/app/renders")
PREVIEW_DIR = RENDERS_DIR / "_preview"


# --- /imagecheck (diagnostica) -------------------------------------------

@router.get("/imagecheck")
def imagecheck():
    """Diagnostica completa per debug image generation.

    Restituisce:
    - cosa sta leggendo l'app dal .env (conferma che le variabili sono caricate)
    - quali modelli Gemini sono effettivamente accessibili con la chiave
    - separazione tra modelli di image generation e text generation
    """
    out: dict[str, Any] = {
        "config_loaded": {
            "DEFAULT_IMAGE_SOURCE": settings.DEFAULT_IMAGE_SOURCE,
            "GEMINI_IMAGE_MODEL": settings.GEMINI_IMAGE_MODEL,
            "IMAGEN_MODEL": settings.IMAGEN_MODEL,
            "POLLINATIONS_MODEL": settings.POLLINATIONS_MODEL,
            "google_api_key_present": bool(settings.GOOGLE_API_KEY),
            "gemini_api_key_present": bool(settings.GEMINI_API_KEY),
            "unsplash_key_present": bool(settings.UNSPLASH_ACCESS_KEY),
            "active_image_key": (
                "GEMINI_API_KEY" if settings.GEMINI_API_KEY
                else ("GOOGLE_API_KEY" if settings.GOOGLE_API_KEY else "none")
            ),
        },
        "google_models": None,
        "errors": [],
    }

    key = settings.gemini_image_key
    if not key:
        out["errors"].append("Nessuna chiave Google configurata, skip ListModels")
        return out

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        r = httpx.get(url, timeout=20.0)
        if r.status_code != 200:
            out["errors"].append(f"ListModels HTTP {r.status_code}: {r.text[:200]}")
            return out
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        out["errors"].append(f"ListModels failed: {e}")
        return out

    all_models = data.get("models") or []
    image_capable = []
    text_capable = []
    for m in all_models:
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods") or []
        is_image = "image" in name.lower() or "imagen" in name.lower()
        if is_image:
            image_capable.append({
                "name": name,
                "display": m.get("displayName"),
                "methods": methods,
                "input_token_limit": m.get("inputTokenLimit"),
                "description": (m.get("description") or "")[:160],
            })
        elif "generateContent" in methods:
            text_capable.append({
                "name": name,
                "display": m.get("displayName"),
            })

    out["google_models"] = {
        "total": len(all_models),
        "image_capable": image_capable,
        "text_capable_sample": text_capable[:5],  # solo primi 5 per non riempire il payload
        "configured_model_present": any(
            m["name"].endswith(settings.GEMINI_IMAGE_MODEL) for m in image_capable
        ),
    }
    return out


# --- /variants -----------------------------------------------------------

class VariantsRequest(BaseModel):
    visual_hint: str
    source: str = "gemini_image"        # ai | gemini_image | wikimedia | unsplash
    n: int = Field(default=3, ge=1, le=6)
    aspect_ratio: str = "3:4"
    is_cover: bool = True


@router.post("/variants")
def generate_variants(req: VariantsRequest):
    """Genera N varianti immagine per un singolo visual_hint.

    Salva le PNG in renders/_preview/{session_uuid}/v_{i}.png e ritorna gli URL.
    NON crea record in DB — questo serve solo per la scelta in step 2 del wizard.
    """
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex[:12]
    out_dir = PREVIEW_DIR / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    errors: list[str] = []

    diag: dict[str, Any] = {}
    # SHORTCUT Wikimedia: una sola API call con diagnostica completa
    if req.source.lower() == "wikimedia":
        wm = WikimediaSearch()
        try:
            hits = wm.search_multi(req.visual_hint, n=req.n, diagnostics=diag)
        except Exception as e:  # noqa: BLE001
            errors.append(f"wikimedia: {e}")
            hits = []
        if not hits:
            # Costruisce un messaggio chiaro elencando tutte le strategie tentate
            tried = diag.get("queries_tried") or []
            tried_summary = " → ".join(
                f"{t.get('via', '?')}({t.get('q', '?')[:25]})={t.get('raw', t.get('hits', t.get('error', '?')))}"
                for t in tried
            )
            errors.append(
                f"Wikimedia: nessun risultato dopo {len(tried)} tentativi. "
                f"Strategie: {tried_summary}. "
                "Prova nomi propri famosi (Alan Turing, Dartmouth College) o concetti generici (dental clinic, microscope)."
            )
        for i, hit in enumerate(hits, start=1):
            path = out_dir / f"v_{i}.png"
            path.write_bytes(hit.data)
            results.append({
                "index": i,
                "url": f"/renders/_preview/{session_id}/{path.name}",
                "attribution": hit.attribution_line(),
            })
    else:
        for i in range(req.n):
            try:
                data = _generate_one(
                    source=req.source,
                    visual_hint=req.visual_hint,
                    aspect_ratio=req.aspect_ratio,
                    is_cover=req.is_cover,
                    variant_index=i,
                )
            except (ImageGenError, ValueError, RuntimeError) as e:
                logger.warning("variant %d failed: %s", i + 1, e)
                errors.append(f"#{i + 1}: {e}")
                continue
            if not data:
                errors.append(f"#{i + 1}: no result")
                continue
            path = out_dir / f"v_{i + 1}.png"
            path.write_bytes(data)
            results.append({
                "index": i + 1,
                "url": f"/renders/_preview/{session_id}/{path.name}",
            })

    return {
        "session_id": session_id,
        "source": req.source,
        "variants": results,
        "errors": errors,
        "wikimedia_diag": diag if req.source.lower() == "wikimedia" else None,
    }


# --- /wikimedia-debug (debug query Wikimedia senza filtri) ---------------

@router.get("/wikimedia-debug")
def wikimedia_debug(q: str, limit: int = 10):
    """Cerca su Wikimedia con `q` e ritorna TUTTI i risultati raw, senza filtri.

    Usalo per capire cosa risponde Wikimedia alla tua query specifica.
    Esempio: GET /api/wizard/wikimedia-debug?q=Alan+Turing+portrait
    """
    import time
    import httpx
    user_agent = (
        "dental-ai-content/0.1 (Instagram personal brand; "
        "https://instagram.com/dr.valenti)"
    )
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "generator": "search",
        "gsrsearch": q, "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|mime",
        "format": "json", "formatversion": "2",
    }
    try:
        r = httpx.get(url, params=params, timeout=20.0,
                      headers={"User-Agent": user_agent, "Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return {"query": q, "error": str(e)}

    pages = (data.get("query") or {}).get("pages") or []
    out = []
    for p in pages:
        info = (p.get("imageinfo") or [None])[0] or {}
        out.append({
            "title": p.get("title"),
            "url": info.get("url"),
            "width": info.get("width"),
            "height": info.get("height"),
            "mime": info.get("mime"),
            "would_pass_ext_filter": (info.get("url") or "").lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif")
            ),
            "would_pass_size_filter": max(
                int(info.get("width") or 0), int(info.get("height") or 0)
            ) >= 400,
        })
    return {
        "query": q,
        "total_pages": len(pages),
        "results": out,
        "raw_response_keys": list(data.keys()),
    }


# Suffissi diversi per ogni variante Wikimedia → 3 risultati diversi senza hammerare
WIKIMEDIA_VARIANT_SUFFIX = ["", " portrait", " historical photograph"]


def _generate_one(*, source: str, visual_hint: str, aspect_ratio: str,
                  is_cover: bool, variant_index: int = 0) -> Optional[bytes]:
    s = source.lower()
    if s == "pollinations":
        prov = PollinationsProvider(settings.POLLINATIONS_MODEL)
        return prov.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio=aspect_ratio)
    if s == "gemini_image":
        key = settings.gemini_image_key
        if not key:
            raise ImageGenError("GEMINI_API_KEY (o GOOGLE_API_KEY) non configurata")
        prov = GeminiImageProvider(key, settings.GEMINI_IMAGE_MODEL)
        return prov.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio=aspect_ratio)
    if s == "ai":
        if not settings.GOOGLE_API_KEY:
            raise ImageGenError("GOOGLE_API_KEY non configurata")
        prov = ImagenProvider(settings.GOOGLE_API_KEY, settings.IMAGEN_MODEL)
        return prov.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio=aspect_ratio)
    if s == "wikimedia":
        # UNA sola search per variante (no piu' loop di 6) usando suffix diversi.
        wm = WikimediaSearch()
        sfx = WIKIMEDIA_VARIANT_SUFFIX[variant_index % len(WIKIMEDIA_VARIANT_SUFFIX)]
        hit = wm.search((visual_hint + sfx).strip())
        return hit.data if hit else None
    if s == "unsplash":
        us = UnsplashSearch(settings.UNSPLASH_ACCESS_KEY)
        hit = us.search(visual_hint)
        return hit.data if hit else None
    raise ValueError(f"source non valido: {source}")


# --- /upload-image (immagine custom dell'utente) -------------------------

ALLOWED_UPLOAD_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_UPLOAD_SIZE = 15 * 1024 * 1024  # 15 MB


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """L'utente carica un'immagine custom da usare come sfondo.

    Salva in renders/_preview/{session_id}/upload_{N}.{ext} e restituisce
    l'URL utilizzabile come `selectedVariant.url` nel wizard.
    """
    if file.content_type not in ALLOWED_UPLOAD_MIME:
        raise HTTPException(400, f"Formato non supportato: {file.content_type}. Usa PNG/JPG/WebP.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File troppo grande ({len(data)} bytes). Max {MAX_UPLOAD_SIZE // 1024 // 1024} MB.")
    if len(data) < 100:
        raise HTTPException(400, "File vuoto o corrotto.")

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex[:12]
    out_dir = PREVIEW_DIR / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = {
        "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp",
    }[file.content_type]
    path = out_dir / f"upload.{ext}"
    path.write_bytes(data)

    return {
        "session_id": session_id,
        "url": f"/renders/_preview/{session_id}/{path.name}",
        "size_bytes": len(data),
        "filename": file.filename,
    }


# --- /finalize -----------------------------------------------------------

class WizardSlideData(BaseModel):
    index: int = Field(ge=1)
    png_base64: str  # esportato dal canvas Fabric.js


class WizardFinalizeRequest(BaseModel):
    kind: str
    title: str
    hook: Optional[str] = None
    caption: str
    hashtags: str = ""
    cta: Optional[str] = None
    reel_script: Optional[str] = None
    slides_meta: list[dict[str, Any]] = []  # title/body/visual_hint per slide (per audit)
    slides_png: list[WizardSlideData]
    provider: str = "wizard"
    model: Optional[str] = None
    paper_id: Optional[int] = None
    prompt: Optional[str] = None


@router.post("/finalize", response_model=ContentOut)
def finalize_wizard(req: WizardFinalizeRequest, db: Session = Depends(get_db)):
    """Salva i PNG editati nel canvas + i metadati testuali come Content."""
    if not req.slides_png:
        raise HTTPException(400, "Nessuna slide fornita.")

    # 1) Valida il testo (regole standard)
    val = validate_content_rules(
        kind=req.kind, title=req.title, caption=req.caption,
        hashtags=req.hashtags, slides=req.slides_meta,
        reel_script=req.reel_script,
    )

    # 2) Crea record Content
    content = Content(
        paper_id=req.paper_id, kind=req.kind, title=req.title or "Senza titolo",
        hook=req.hook, caption=req.caption, hashtags=req.hashtags, cta=req.cta,
        slides_json=req.slides_meta or None, reel_script=req.reel_script,
        provider=req.provider, model=req.model, prompt=req.prompt,
        validation_json=val.as_dict(), status="draft",
    )
    db.add(content)
    db.commit()
    db.refresh(content)

    # 3) Salva i PNG nel folder del content
    out_dir = RENDERS_DIR / str(content.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    # ripulisci eventuali render precedenti
    for f in out_dir.glob("*.png"):
        try:
            f.unlink()
        except OSError:
            pass

    for slide in sorted(req.slides_png, key=lambda s: s.index):
        b64 = slide.png_base64
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            data = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, f"PNG base64 invalido per slide {slide.index}: {e}")
        prefix = "scene" if req.kind == "reel" else "slide"
        if req.kind == "story" and slide.index == 1 and len(req.slides_png) == 1:
            name = "story.png"
        elif req.kind == "post" and slide.index == 1 and len(req.slides_png) == 1:
            name = "main.png"
        else:
            name = f"{prefix}_{slide.index:02d}.png"
        (out_dir / name).write_bytes(data)

    return content
