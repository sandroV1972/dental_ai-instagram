"""Pubblicazione Instagram tramite Meta Graph API.

Documentazione ufficiale: https://developers.facebook.com/docs/instagram-api

Workflow OAuth:
1. L'utente apre /api/publish/oauth/start (redirect a Meta auth)
2. Meta richiede consenso, redirige a /api/publish/oauth/callback?code=...
3. Il backend scambia il code per un short-lived token, poi lo trasforma in
   un long-lived token (60gg)
4. Il long-lived token viene salvato in .env_publishing (file separato)

Workflow Publish:
1. Tutte le immagini DEVONO essere accessibili da URL PUBBLICI HTTPS
   (Meta scarica le immagini dal nostro server; localhost NON funziona).
   In dev: usa ngrok / cloudflared. In prod: dominio + reverse proxy.
2. Per ogni immagine: POST /{ig_user_id}/media → ottieni media_id
3. Per carousel: POST /{ig_user_id}/media con children=[media_ids,...]
4. Pubblica: POST /{ig_user_id}/media_publish con creation_id
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from ...core.config import settings

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
META_OAUTH_BASE = "https://www.facebook.com/{ver}/dialog/oauth".format(ver=GRAPH_VERSION)

# Scope minimi per pubblicare contenuti Instagram Business
OAUTH_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
]


class PublishingNotConfigured(RuntimeError):
    """Sollevato quando le credenziali Meta App o IG account non sono configurate."""


class InstagramError(RuntimeError):
    """Errore durante una chiamata a Graph API."""


# --- OAuth helpers -------------------------------------------------------

def build_oauth_url(state: str = "default") -> str:
    """Costruisce l'URL a cui redirezionare l'utente per l'autorizzazione Meta."""
    if not settings.META_APP_ID:
        raise PublishingNotConfigured(
            "META_APP_ID non configurata. Crea la tua App su developers.facebook.com."
        )
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": settings.META_REDIRECT_URI,
        "scope": ",".join(OAUTH_SCOPES),
        "response_type": "code",
        "state": state,
    }
    return f"{META_OAUTH_BASE}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Scambia il code OAuth per short-lived → long-lived token (60gg)."""
    if not (settings.META_APP_ID and settings.META_APP_SECRET):
        raise PublishingNotConfigured("META_APP_ID/META_APP_SECRET non configurati.")

    # Step 1: code → short-lived token
    short_url = f"{GRAPH_BASE}/oauth/access_token"
    try:
        r = httpx.get(short_url, params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        }, timeout=30.0)
        r.raise_for_status()
        short = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise InstagramError(f"OAuth code exchange failed: {e}") from e

    short_token = short.get("access_token")
    if not short_token:
        raise InstagramError(f"OAuth response senza access_token: {short}")

    # Step 2: short → long-lived (60gg)
    long_url = f"{GRAPH_BASE}/oauth/access_token"
    try:
        r = httpx.get(long_url, params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": short_token,
        }, timeout=30.0)
        r.raise_for_status()
        long_data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise InstagramError(f"Long-lived token exchange failed: {e}") from e

    return {
        "short_lived_token": short_token,
        "long_lived_token": long_data.get("access_token"),
        "expires_in": long_data.get("expires_in"),
        "token_type": long_data.get("token_type"),
    }


def save_token_to_file(token: str, expires_in: Optional[int] = None):
    """Salva il long-lived token in un file separato (`.ig_token`).
    L'utente lo deve poi copiare manualmente in IG_LONG_LIVED_TOKEN nel `.env`,
    oppure caricarlo all'avvio.
    """
    path = Path("/app") / ".ig_token"
    content = f"IG_LONG_LIVED_TOKEN={token}\n"
    if expires_in:
        content += f"# expires_in_sec={expires_in}\n"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        logger.warning("Impossibile salvare .ig_token: %s", e)


# --- Status / config check ----------------------------------------------

def publishing_status() -> dict[str, Any]:
    """Ritorna lo stato di configurazione per la dashboard."""
    return {
        "meta_app_configured": bool(settings.META_APP_ID and settings.META_APP_SECRET),
        "token_present": bool(settings.IG_LONG_LIVED_TOKEN),
        "ig_business_account_id_set": bool(settings.IG_BUSINESS_ACCOUNT_ID),
        "public_base_url_set": bool(settings.PUBLIC_BASE_URL),
        "redirect_uri": settings.META_REDIRECT_URI,
        "scopes": OAUTH_SCOPES,
        "ready_to_publish": all([
            settings.IG_LONG_LIVED_TOKEN,
            settings.IG_BUSINESS_ACCOUNT_ID,
            settings.PUBLIC_BASE_URL,
        ]),
    }


# --- Pubblicazione effettiva --------------------------------------------

@dataclass
class PublishResult:
    media_id: str
    permalink: Optional[str] = None
    raw: Optional[dict] = None


class InstagramPublisher:
    """Wrapper alle chiamate Graph API per pubblicare contenuti IG."""

    def __init__(self, ig_user_id: Optional[str] = None, token: Optional[str] = None):
        self.ig_user_id = ig_user_id or settings.IG_BUSINESS_ACCOUNT_ID
        self.token = token or settings.IG_LONG_LIVED_TOKEN
        if not self.ig_user_id:
            raise PublishingNotConfigured("IG_BUSINESS_ACCOUNT_ID non configurato.")
        if not self.token:
            raise PublishingNotConfigured("IG_LONG_LIVED_TOKEN non configurato. Esegui OAuth flow.")
        if not settings.PUBLIC_BASE_URL:
            raise PublishingNotConfigured(
                "PUBLIC_BASE_URL non configurato. Meta deve poter scaricare le immagini "
                "da un URL pubblico HTTPS (usa ngrok in dev: 'ngrok http 8000')."
            )

    def _create_image_container(self, image_url: str, caption: Optional[str] = None,
                                is_carousel_item: bool = False) -> str:
        """POST /{ig_user_id}/media → ritorna il container id."""
        params = {"image_url": image_url, "access_token": self.token}
        if caption and not is_carousel_item:
            params["caption"] = caption
        if is_carousel_item:
            params["is_carousel_item"] = "true"
        try:
            r = httpx.post(f"{GRAPH_BASE}/{self.ig_user_id}/media", params=params, timeout=60.0)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise InstagramError(f"Create image container failed: {e}") from e
        cid = data.get("id")
        if not cid:
            raise InstagramError(f"Container creation: id mancante. Response: {data}")
        return cid

    def _create_carousel_container(self, children_ids: list[str], caption: str) -> str:
        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "caption": caption,
            "access_token": self.token,
        }
        try:
            r = httpx.post(f"{GRAPH_BASE}/{self.ig_user_id}/media", params=params, timeout=60.0)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise InstagramError(f"Create carousel container failed: {e}") from e
        cid = data.get("id")
        if not cid:
            raise InstagramError(f"Carousel container: id mancante. Response: {data}")
        return cid

    def _publish(self, creation_id: str) -> PublishResult:
        params = {"creation_id": creation_id, "access_token": self.token}
        try:
            r = httpx.post(f"{GRAPH_BASE}/{self.ig_user_id}/media_publish",
                          params=params, timeout=60.0)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise InstagramError(f"Publish failed: {e}") from e
        media_id = data.get("id")
        if not media_id:
            raise InstagramError(f"Publish: id mancante. Response: {data}")
        return PublishResult(media_id=media_id, raw=data)

    # --- API pubbliche ---

    def publish_single_photo(self, image_url: str, caption: str) -> PublishResult:
        container_id = self._create_image_container(image_url, caption=caption)
        return self._publish(container_id)

    def publish_carousel(self, image_urls: list[str], caption: str) -> PublishResult:
        if not (2 <= len(image_urls) <= 10):
            raise InstagramError("Carousel: tra 2 e 10 immagini, fornite {}".format(len(image_urls)))
        children = [self._create_image_container(u, is_carousel_item=True) for u in image_urls]
        container_id = self._create_carousel_container(children, caption=caption)
        return self._publish(container_id)

    def publish_story(self, image_url: str) -> PublishResult:
        # Le story NON supportano caption nella POST: i media type "STORIES" non hanno text overlay
        params = {
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": self.token,
        }
        try:
            r = httpx.post(f"{GRAPH_BASE}/{self.ig_user_id}/media", params=params, timeout=60.0)
            r.raise_for_status()
            container_id = r.json().get("id")
        except (httpx.HTTPError, ValueError) as e:
            raise InstagramError(f"Create story container failed: {e}") from e
        if not container_id:
            raise InstagramError("Story container: id mancante.")
        return self._publish(container_id)
