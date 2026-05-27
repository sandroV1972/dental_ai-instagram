"""Endpoint /api/publish — OAuth Meta + pubblicazione Instagram."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Content
from ..services.publishing import (
    InstagramError, InstagramPublisher, PublishingNotConfigured,
    build_oauth_url, exchange_code_for_token,
)
from ..services.publishing.instagram import publishing_status, save_token_to_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
def status():
    """Diagnostica setup Instagram publishing."""
    return publishing_status()


@router.get("/oauth/start")
def oauth_start():
    """Redirect browser to Meta OAuth consent screen."""
    try:
        url = build_oauth_url()
    except PublishingNotConfigured as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url)


@router.get("/oauth/callback")
def oauth_callback(code: str = Query(...), state: str = Query(default="")):
    """Meta redirect callback: exchange code → long-lived token."""
    try:
        tokens = exchange_code_for_token(code)
    except (PublishingNotConfigured, InstagramError) as e:
        return HTMLResponse(f"""
            <h2>OAuth fallito</h2>
            <p style='color:#b91c1c'>{e}</p>
            <p><a href='/'>Torna alla dashboard</a></p>
        """, status_code=400)
    long_token = tokens.get("long_lived_token")
    if long_token:
        save_token_to_file(long_token, expires_in=tokens.get("expires_in"))
    return HTMLResponse(f"""
        <h2 style='color:#059669'>OAuth completato!</h2>
        <p>Long-lived token generato. Validità: ~{tokens.get('expires_in', 'n/d')} sec (~60 giorni).</p>
        <p><b>IMPORTANTE</b>: copia questo token nel tuo file <code>.env</code> alla riga:</p>
        <pre style='background:#f3f4f6;padding:1em;border-radius:6px;word-break:break-all'>IG_LONG_LIVED_TOKEN={long_token}</pre>
        <p>Poi <code>docker compose restart api</code>.</p>
        <p>Devi anche recuperare il tuo <b>Instagram Business Account ID</b> e impostarlo come
        <code>IG_BUSINESS_ACCOUNT_ID</code>. Lo trovi via:</p>
        <pre style='background:#f3f4f6;padding:1em;border-radius:6px'>curl 'https://graph.facebook.com/v21.0/me/accounts?access_token={long_token}'</pre>
        <p>Cerca il <code>page_id</code>, poi:</p>
        <pre style='background:#f3f4f6;padding:1em;border-radius:6px'>curl 'https://graph.facebook.com/v21.0/&lt;PAGE_ID&gt;?fields=instagram_business_account&access_token={long_token}'</pre>
        <p><a href='/'>Torna alla dashboard</a></p>
    """)


@router.post("/{content_id}")
def publish_to_instagram(content_id: int, db: Session = Depends(get_db)):
    """Pubblica un Content approvato su Instagram.

    Richiede:
    - Content in stato 'approved' o 'scheduled'
    - PUBLIC_BASE_URL configurata (es. https://abc123.ngrok.io)
    - Token IG long-lived attivo
    - IG Business Account ID configurato
    """
    c = db.get(Content, content_id)
    if not c:
        raise HTTPException(404, "Content non trovato")
    if c.status not in ("approved", "scheduled"):
        raise HTTPException(400, f"Status {c.status}: serve 'approved' o 'scheduled'.")

    try:
        publisher = InstagramPublisher()
    except PublishingNotConfigured as e:
        raise HTTPException(400, str(e))

    # Costruisci URL pubblici delle immagini
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    from pathlib import Path
    renders_dir = Path("/app/renders") / str(content_id)
    if not renders_dir.is_dir():
        raise HTTPException(400, f"Nessuna immagine renderizzata per Content #{content_id}")
    png_files = sorted(renders_dir.glob("*.png"))
    if not png_files:
        raise HTTPException(400, "Nessun PNG trovato. Genera prima le immagini.")
    image_urls = [f"{base}/renders/{content_id}/{p.name}" for p in png_files]

    # Caption completa con hashtag
    full_caption = c.caption + ("\n\n" + c.hashtags if c.hashtags else "")

    try:
        if c.kind == "story":
            result = publisher.publish_story(image_urls[0])
        elif c.kind in ("post",) or (len(image_urls) == 1 and c.kind != "carousel"):
            result = publisher.publish_single_photo(image_urls[0], full_caption)
        else:
            # carousel / myth_reality / infographic / paper_commentary multi-slide
            if len(image_urls) < 2:
                result = publisher.publish_single_photo(image_urls[0], full_caption)
            else:
                result = publisher.publish_carousel(image_urls[:10], full_caption)
    except InstagramError as e:
        raise HTTPException(502, f"Pubblicazione fallita: {e}")

    c.status = "published"
    c.published_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "ok": True,
        "media_id": result.media_id,
        "permalink": result.permalink,
        "image_count": len(image_urls),
    }
