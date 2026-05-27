"""Endpoint /api/render — genera PNG dei carousel/post e li serve come file statici."""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Content
from ..services.imagegen import (
    GeminiImageProvider, ImageGenError, ImagenError, ImagenProvider,
    PollinationsProvider, render_slide,
)
from ..services.imagesearch import (
    ImageHit, ImageSearchError, UnsplashSearch, WikimediaSearch,
)
from ..services.video import VideoBuildError, build_reel_video

logger = logging.getLogger(__name__)
router = APIRouter()

# Directory dove vengono salvati i PNG; montata in docker-compose come ./renders
RENDERS_DIR = Path("/app/renders")


def _ensure_dir() -> None:
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)


def _content_dir(cid: int) -> Path:
    d = RENDERS_DIR / str(cid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clear_dir(d: Path) -> None:
    for f in d.glob("*.png"):
        try:
            f.unlink()
        except OSError as e:
            logger.warning("cannot delete %s: %s", f, e)


class _BgFetcher:
    """Astrae la sorgente immagini scelta dall'utente per un singolo render.

    Strategia: instanzia il provider piu' adatto e per ogni slide chiama
    `fetch(visual_hint)`. Su errore tiene traccia del messaggio in `errors`
    (visibile poi nella response API per dare feedback all'utente).
    """

    def __init__(self, source: str):
        self.source = source
        self.imagen_ai: ImagenProvider | None = None
        self.gemini_image: GeminiImageProvider | None = None
        self.pollinations: PollinationsProvider | None = None
        self.wm: WikimediaSearch | None = None
        self.unsplash: UnsplashSearch | None = None
        self.hits: list[tuple[int, ImageHit]] = []
        self.errors: list[dict] = []
        self.init_error: str | None = None

        try:
            if source == "ai":
                if not settings.GOOGLE_API_KEY:
                    raise ImagenError("GOOGLE_API_KEY non configurata")
                self.imagen_ai = ImagenProvider(settings.GOOGLE_API_KEY, settings.IMAGEN_MODEL)
            elif source == "gemini_image":
                key = settings.gemini_image_key
                if not key:
                    raise ImageGenError("GEMINI_API_KEY (o GOOGLE_API_KEY) non configurata")
                self.gemini_image = GeminiImageProvider(key, settings.GEMINI_IMAGE_MODEL)
            elif source == "pollinations":
                self.pollinations = PollinationsProvider(settings.POLLINATIONS_MODEL)
            elif source == "wikimedia":
                self.wm = WikimediaSearch()
            elif source == "unsplash":
                self.unsplash = UnsplashSearch(settings.UNSPLASH_ACCESS_KEY)
            elif source == "none":
                pass
            else:
                raise ValueError(f"image_source non valido: {source}")
        except (ImageGenError, ImagenError, ImageSearchError, ValueError) as e:
            self.init_error = str(e)
            logger.warning("BgFetcher init failed for source=%s: %s", source, e)

    def _record_error(self, slide_index: int, message: str):
        self.errors.append({
            "slide": slide_index,
            "source": self.source,
            "message": message,
            "hint": _hint_for_error(self.source, message),
        })

    def fetch(self, visual_hint: str, *, slide_index: int, is_cover: bool) -> bytes | None:
        if self.init_error and not self.errors:
            # log dell'errore di init UNA volta sola (visualizzato in UI)
            self._record_error(slide_index=0, message=self.init_error)
        if not visual_hint:
            return None
        try:
            if self.imagen_ai:
                return self.imagen_ai.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio="3:4")
            if self.gemini_image:
                return self.gemini_image.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio="3:4")
            if self.pollinations:
                return self.pollinations.generate(visual_hint=visual_hint, is_cover=is_cover, aspect_ratio="3:4")
            if self.wm:
                hit = self.wm.search(visual_hint)
                if hit:
                    self.hits.append((slide_index, hit))
                    return hit.data
                self._record_error(slide_index, "Wikimedia: nessun risultato per questo visual_hint")
                return None
            if self.unsplash:
                hit = self.unsplash.search(visual_hint)
                if hit:
                    self.hits.append((slide_index, hit))
                    return hit.data
                self._record_error(slide_index, "Unsplash: nessun risultato per questo visual_hint")
                return None
        except (ImageGenError, ImagenError, ImageSearchError) as e:
            msg = str(e)
            self._record_error(slide_index, msg)
            logger.warning("BgFetcher.fetch failed (slide %d, source=%s): %s",
                           slide_index, self.source, msg)
        return None


def _hint_for_error(source: str, message: str) -> str:
    """Suggerimento rivolto all'utente per risolvere l'errore."""
    m = (message or "").lower()
    if source == "ai" and any(k in m for k in ("403", "forbidden", "permission", "billing", "not enabled")):
        return ("Imagen 3 richiede billing attivo su Google Cloud. "
                "Soluzione gratis: usa 'gemini_image' (Nano Banana, free tier).")
    if source == "ai" and "not found" in m:
        return "Modello Imagen non disponibile sulla tua chiave. Prova 'gemini_image'."
    if source == "gemini_image" and "429" in m:
        return "Rate limit del free tier raggiunto (15 req/min). Attendi 1 minuto e riprova."
    if source == "unsplash" and "401" in m:
        return "UNSPLASH_ACCESS_KEY mancante o invalida. Registrati su unsplash.com/developers."
    if "no result" in m or "no risult" in m or "nessun risultato" in m:
        return "Riformula il visual_hint (es. termini piu' generici/in inglese)."
    return ""


@router.post("/{cid}")
def render_content(
    cid: int,
    db: Session = Depends(get_db),
    image_source: str | None = None,
):
    """Renderizza tutte le slide di un Content come PNG.

    Query param `image_source`:
    - "ai"        → Gemini Imagen (genera immagini su misura, costa $)
    - "wikimedia" → Wikimedia Commons (CC / public domain, gratis)
    - "unsplash"  → Unsplash stock photos (free, richiede UNSPLASH_ACCESS_KEY)
    - "none"      → gradient brand, nessuna immagine
    Default: settings.DEFAULT_IMAGE_SOURCE.

    Su qualsiasi errore del provider scelto (no quota, no credenziali, no match)
    la singola slide cade sul gradient brand senza interrompere il render.

    Per le sorgenti CC, l'attribution viene allegata nella response come
    `attributions` e salvata accanto agli asset come `attribution.txt`.
    """
    _ensure_dir()
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")

    out_dir = _content_dir(cid)
    _clear_dir(out_dir)

    source = (image_source or settings.DEFAULT_IMAGE_SOURCE).lower()
    if source not in ("ai", "gemini_image", "pollinations", "wikimedia", "unsplash", "none"):
        raise HTTPException(400, f"image_source non valido: {source}")
    fetcher = _BgFetcher(source)

    slides = c.slides_json if isinstance(c.slides_json, list) else []
    images: list[str] = []

    if c.kind in ("carousel", "myth_reality", "infographic") and slides:
        total = len(slides)
        for i, s in enumerate(slides, start=1):
            visual_hint = (s or {}).get("visual_hint") or ""
            bg = fetcher.fetch(visual_hint, slide_index=i, is_cover=(i == 1))
            png = render_slide(
                canvas="carousel",
                title=(s or {}).get("title") or c.title,
                body=(s or {}).get("body") or "",
                slide_index=i,
                slide_total=total,
                author_name=settings.AUTHOR_NAME,
                handle=settings.INSTAGRAM_HANDLE,
                tagline=settings.BRAND_TAGLINE,
                background_image=bg,
                is_cover=(i == 1),
                is_cta=(i == total and total >= 2),
            )
            path = out_dir / f"slide_{i:02d}.png"
            path.write_bytes(png)
            images.append(f"/renders/{cid}/{path.name}")
    elif c.kind == "reel":
        # Reel: una scena per slide in formato verticale 1080x1920
        # Se l'AI non ha fornito slides, ripiega su una cover singola
        scenes = slides if slides else [{
            "index": 1, "title": c.title, "body": c.hook or "",
            "visual_hint": c.title,
        }]
        total = len(scenes)
        for i, s in enumerate(scenes, start=1):
            vh = (s or {}).get("visual_hint") or c.title
            bg = fetcher.fetch(vh, slide_index=i, is_cover=(i == 1))
            png = render_slide(
                canvas="reel_cover",
                title=(s or {}).get("title") or c.title,
                body=(s or {}).get("body") or "",
                slide_index=i,
                slide_total=total,
                author_name=settings.AUTHOR_NAME,
                handle=settings.INSTAGRAM_HANDLE,
                tagline=settings.BRAND_TAGLINE,
                background_image=bg,
                is_cover=(i == 1),
                is_cta=(i == total and total >= 2),
            )
            path = out_dir / f"scene_{i:02d}.png"
            path.write_bytes(png)
            images.append(f"/renders/{cid}/{path.name}")
    elif c.kind == "story":
        # Story: una sola immagine verticale 1080x1920
        # I dati arrivano dai field top-level del Content (no slides_json per le story)
        vh = c.title
        # Se ci sono slides legacy con visual_hint, usalo
        if slides and slides[0].get("visual_hint"):
            vh = slides[0]["visual_hint"]
        bg = fetcher.fetch(vh, slide_index=1, is_cover=True)
        png = render_slide(
            canvas="story",
            title=c.title,
            body=c.hook or "",
            slide_index=1, slide_total=1,
            author_name=settings.AUTHOR_NAME,
            handle=settings.INSTAGRAM_HANDLE,
            tagline=settings.BRAND_TAGLINE,
            background_image=bg,
            is_cover=True,
        )
        path = out_dir / "story.png"
        path.write_bytes(png)
        images.append(f"/renders/{cid}/{path.name}")
    else:
        # post, mini_explainer, paper_commentary, bts, case_study → singola immagine 1080x1080
        vh = (slides[0].get("visual_hint") if slides else "") or c.title
        bg = fetcher.fetch(vh, slide_index=1, is_cover=True)
        png = render_slide(
            canvas="post",
            title=c.title,
            body=c.hook or "",
            slide_index=1, slide_total=1,
            author_name=settings.AUTHOR_NAME,
            handle=settings.INSTAGRAM_HANDLE,
            tagline=settings.BRAND_TAGLINE,
            background_image=bg,
            is_cover=True,
        )
        path = out_dir / "main.png"
        path.write_bytes(png)
        images.append(f"/renders/{cid}/{path.name}")

    # Attribution per le sorgenti CC (vuoto per "ai" e "none")
    attributions = [
        {
            "slide": idx,
            "source": hit.source,
            "title": hit.title,
            "author": hit.author,
            "license": hit.license,
            "license_url": hit.license_url,
            "page_url": hit.page_url,
            "line": hit.attribution_line(),
        }
        for idx, hit in fetcher.hits
    ]
    if attributions:
        attr_text = "\n".join(f"Slide {a['slide']}: {a['line']}" for a in attributions)
        (out_dir / "attribution.txt").write_text(attr_text, encoding="utf-8")

    return {
        "images": images,
        "count": len(images),
        "source": source,
        "attributions": attributions,
        "errors": fetcher.errors,
        "init_error": fetcher.init_error,
    }


@router.post("/{cid}/video")
def render_video(cid: int, db: Session = Depends(get_db),
                 per_slide: float = 3.5, xfade: float = 0.6):
    """Compone un video MP4 verticale (1080x1920) dalle scene del reel.

    Richiede che le slide (scene) siano già renderizzate via POST /api/render/{cid}.
    Solo per content di tipo 'reel'. Per altri kind ritorna 400.

    Query params:
    - per_slide: durata di ciascuna scena in secondi (default 3.5)
    - xfade: durata del crossfade tra scene consecutive (default 0.6)
    """
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    if c.kind != "reel":
        raise HTTPException(400, "Il video reel e' supportato solo per kind='reel'.")

    out_dir = _content_dir(cid)
    scenes = sorted(out_dir.glob("scene_*.png"))
    if not scenes:
        raise HTTPException(
            400,
            "Nessuna scena renderizzata. Lancia prima POST /api/render/{cid} per produrre le scene.",
        )

    video_path = out_dir / "reel.mp4"
    try:
        build_reel_video(
            slide_paths=scenes, output_path=video_path,
            per_slide=per_slide, xfade_duration=xfade,
        )
    except VideoBuildError as e:
        raise HTTPException(502, f"Errore build video: {e}")

    duration_sec = per_slide + (len(scenes) - 1) * (per_slide - xfade)
    return {
        "video": f"/renders/{cid}/reel.mp4",
        "scenes": len(scenes),
        "duration_sec": round(duration_sec, 2),
    }


@router.get("/{cid}/zip")
def download_zip(cid: int, db: Session = Depends(get_db)):
    """Scarica tutte le immagini del Content come zip (utile per Buffer/Later)."""
    c = db.get(Content, cid)
    if not c:
        raise HTTPException(404, "Content non trovato")
    out_dir = _content_dir(cid)
    files = sorted(out_dir.glob("*.png"))
    if not files:
        raise HTTPException(400, "Nessuna immagine renderizzata. Lancia prima POST /api/render/{cid}.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
        # aggiungiamo anche la caption e gli hashtag, comodi da copiare
        caption_text = (
            f"{c.title}\n\n{c.caption}\n\n{c.hashtags}"
            if c.hashtags else f"{c.title}\n\n{c.caption}"
        )
        zf.writestr("caption.txt", caption_text)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="content_{cid}.zip"'},
    )
