"""Unsplash search (foto stock free, alta qualita').

API docs: https://unsplash.com/documentation
Header obbligatorio: Authorization: Client-ID <access_key>
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from .types import ImageHit, ImageSearchError

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.unsplash.com/search/photos"


class UnsplashSearch:
    def __init__(self, access_key: Optional[str]):
        if not access_key:
            raise ImageSearchError("UNSPLASH_ACCESS_KEY non configurata")
        self.access_key = access_key
        self._client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Client-ID {access_key}",
                "Accept-Version": "v1",
            },
        )

    def search(self, query: str, *, orientation: str = "portrait") -> Optional[ImageHit]:
        """Cerca la prima foto rilevante. Ritorna None se nessun match."""
        if not (query or "").strip():
            return None
        params = {
            "query": query,
            "per_page": 5,
            "orientation": orientation,
            "content_filter": "high",
        }
        try:
            r = self._client.get(SEARCH_URL, params=params)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise ImageSearchError(f"Unsplash API error: {e}") from e
        except ValueError as e:
            raise ImageSearchError(f"Unsplash non-JSON response: {e}") from e

        results = data.get("results") or []
        if not results:
            return None
        first = results[0]
        urls = first.get("urls") or {}
        # "regular" e' ~1080px, sufficiente per il nostro canvas 1080x1350
        download_url = urls.get("regular") or urls.get("full")
        if not download_url:
            return None
        user = (first.get("user") or {})
        author = user.get("name") or user.get("username")
        # Unsplash richiede tracking del download per attribution
        dl_loc = (first.get("links") or {}).get("download_location")
        if dl_loc:
            try:
                self._client.get(dl_loc)  # ping richiesto da TOS
            except httpx.HTTPError:
                pass
        try:
            img = self._client.get(download_url)
            img.raise_for_status()
        except httpx.HTTPError as e:
            raise ImageSearchError(f"Unsplash image download failed: {e}") from e

        return ImageHit(
            data=img.content,
            source="unsplash",
            source_url=download_url,
            page_url=(first.get("links") or {}).get("html", ""),
            title=first.get("alt_description") or first.get("description"),
            author=author,
            license="Unsplash License",
            license_url="https://unsplash.com/license",
        )
