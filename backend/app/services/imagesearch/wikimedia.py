"""Wikimedia Commons search.

API docs: https://commons.wikimedia.org/w/api.php

Flusso:
1. action=query&generator=search&gsrnamespace=6&gsrsearch=<query>   → titoli File:xxx
2. action=query&prop=imageinfo&iiprop=url|extmetadata               → URL + metadata
3. download del file con httpx (rispettando User-Agent come da policy WM)

Filtra immagini troppo piccole (< 600px sul lato lungo) o non supportate.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from .types import ImageHit, ImageSearchError

logger = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Wikimedia policy: User-Agent identificabile con contatto.
# Personalizzabile via env in futuro (per ora hardcoded ma realistico).
USER_AGENT = (
    "dental-ai-content/0.1 (Instagram personal brand; "
    "https://instagram.com/dr.valenti) python-httpx/0.27"
)

ACCEPTED_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MIN_LONG_SIDE = 400  # piu' permissivo: 600 escludeva troppi file storici

# Sleep tra request per non sembrare un bot scriteriato
INTER_REQUEST_SLEEP = 0.4


class WikimediaSearch:
    def __init__(self):
        self._client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Api-User-Agent": USER_AGENT,  # alcuni endpoint Wikimedia preferiscono questo
            },
        )

    def _api_query(self, params: dict, *, retry: int = 2) -> dict:
        """GET con retry esponenziale su 429."""
        delay = 1.0
        last_err = None
        for attempt in range(retry + 1):
            try:
                r = self._client.get(API, params={**params, "format": "json", "formatversion": "2"})
                if r.status_code == 429:
                    last_err = ImageSearchError(
                        f"Wikimedia rate-limit (429). Riprova fra ~{int(delay * (attempt + 1))}s "
                        f"o usa una query piu' specifica (in inglese)."
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as e:
                last_err = ImageSearchError(f"Wikimedia API error: {e}")
                if attempt < retry:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise last_err from e
            except ValueError as e:
                raise ImageSearchError(f"Wikimedia non-JSON response: {e}") from e
        if last_err:
            raise last_err
        raise ImageSearchError("Wikimedia: errore sconosciuto dopo retry")

    def search_multi(self, query: str, *, n: int = 3, limit: int = 15,
                     diagnostics: Optional[dict] = None) -> list[ImageHit]:
        """Strategia in 3 step per massimizzare il match:

        1. Wikipedia article search (per entita' nominate famose tipo persone/luoghi)
           → trova l'articolo, estrae le sue immagini
        2. Commons direct search con la query originale
        3. Commons direct search con query progressivamente semplificate
           (rimuove parole una alla volta dalla fine)

        Si ferma alla prima strategia che ritorna `n` risultati.
        """
        diag = diagnostics if diagnostics is not None else {}
        diag.update({"raw_pages": 0, "filtered_ext": 0, "filtered_size": 0,
                     "filtered_license": 0, "download_failed": 0, "kept": 0,
                     "strategy": None, "queries_tried": []})
        if not (query or "").strip():
            diag["error"] = "empty query"
            return []

        # --- STEP 1: Wikipedia article ---
        try:
            wiki_hits = self._search_via_wikipedia_article(query, n=n)
            if wiki_hits:
                diag["strategy"] = "wikipedia_article"
                diag["kept"] = len(wiki_hits)
                diag["queries_tried"].append({"q": query, "via": "wikipedia", "hits": len(wiki_hits)})
                return wiki_hits
            diag["queries_tried"].append({"q": query, "via": "wikipedia", "hits": 0})
        except Exception as e:  # noqa: BLE001
            logger.warning("Wikipedia article search failed: %s", e)
            diag["queries_tried"].append({"q": query, "via": "wikipedia", "error": str(e)})

        # --- STEP 2: Commons con query originale ---
        hits = self._commons_search_once(query, n=n, limit=limit, diag=diag)
        if hits:
            diag["strategy"] = "commons_full_query"
            return hits

        # --- STEP 3: Commons con query semplificata progressivamente ---
        parts = query.strip().split()
        for cut in range(1, len(parts)):
            shorter = " ".join(parts[:len(parts) - cut])
            if len(shorter) < 3:
                break
            hits = self._commons_search_once(shorter, n=n, limit=limit, diag=diag)
            if hits:
                diag["strategy"] = f"commons_simplified ({len(parts) - cut}/{len(parts)} parole)"
                diag["simplified_query"] = shorter
                return hits

        return []

    def _commons_search_once(self, query: str, *, n: int, limit: int,
                            diag: dict) -> list[ImageHit]:
        """Una singola chiamata Commons. Aggiorna diag in place."""
        time.sleep(INTER_REQUEST_SLEEP)
        try:
            data = self._api_query({
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlheight": 1350,
            })
        except ImageSearchError as e:
            diag["queries_tried"].append({"q": query, "via": "commons", "error": str(e)})
            return []

        pages = (data.get("query") or {}).get("pages") or []
        diag["queries_tried"].append({"q": query, "via": "commons", "raw": len(pages)})
        if not pages:
            return []
        diag["raw_pages"] = max(diag.get("raw_pages", 0), len(pages))

        hits: list[ImageHit] = []
        for page in pages:
            if len(hits) >= n:
                break
            hit, reject_reason = self._page_to_hit_with_reason(page)
            if hit:
                hits.append(hit)
                diag["kept"] = diag.get("kept", 0) + 1
            elif reject_reason:
                diag[reject_reason] = diag.get(reject_reason, 0) + 1
        return hits

    def _search_via_wikipedia_article(self, query: str, *, n: int = 3) -> list[ImageHit]:
        """Per entita' famose: cerca articolo Wikipedia, estrae le sue immagini.

        Molto piu' affidabile di Commons-only per ricerche tipo 'Alan Turing',
        'Dartmouth College', 'John McCarthy', etc.
        """
        # 1. Trova l'articolo
        try:
            r = self._client.get(WIKIPEDIA_API, params={
                "action": "query", "list": "search",
                "srsearch": query, "srlimit": 1,
                "format": "json", "formatversion": "2",
            }, timeout=15.0)
            r.raise_for_status()
            results = ((r.json().get("query") or {}).get("search")) or []
        except (httpx.HTTPError, ValueError):
            return []
        if not results:
            return []
        article_title = results[0]["title"]
        logger.info("Wikipedia: trovato articolo '%s' per query '%s'", article_title, query)

        # 2. Recupera le immagini di quell'articolo
        try:
            r = self._client.get(WIKIPEDIA_API, params={
                "action": "query", "titles": article_title,
                "prop": "images", "imlimit": 25,
                "format": "json", "formatversion": "2",
            }, timeout=15.0)
            r.raise_for_status()
            pages = ((r.json().get("query") or {}).get("pages")) or []
        except (httpx.HTTPError, ValueError):
            return []
        if not pages:
            return []
        # Lista di "File:..." titles
        image_titles = []
        for p in pages:
            for img in (p.get("images") or []):
                t = img.get("title") or ""
                # filtro out icone / SVG / commons-logo etc.
                tl = t.lower()
                if tl.endswith(".svg") or "commons-logo" in tl or "wikidata" in tl:
                    continue
                if any(skip in tl for skip in ("flag of", "icon", "symbol", "edit-icon")):
                    continue
                image_titles.append(t)
        if not image_titles:
            return []

        # 3. Ottieni imageinfo da Commons per quei file (BATCH: una sola call)
        time.sleep(INTER_REQUEST_SLEEP)
        try:
            r = self._client.get(API, params={
                "action": "query",
                "titles": "|".join(image_titles[:25]),  # max 25 per call
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlheight": 1350,
                "format": "json", "formatversion": "2",
            }, timeout=20.0)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return []

        pages = (data.get("query") or {}).get("pages") or []
        hits: list[ImageHit] = []
        for page in pages:
            if len(hits) >= n:
                break
            hit, _reason = self._page_to_hit_with_reason(page)
            if hit:
                hits.append(hit)
        return hits

    def _page_to_hit_with_reason(self, page: dict) -> tuple[Optional[ImageHit], Optional[str]]:
        """Wrapper di _page_to_hit che ritorna anche il motivo del rifiuto."""
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            return None, "filtered_noinfo"
        url = info.get("url") or ""
        if not url.lower().endswith(ACCEPTED_EXT):
            return None, "filtered_ext"
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if max(width, height) < MIN_LONG_SIDE:
            return None, "filtered_size"
        download_url = info.get("thumburl") or url
        meta = info.get("extmetadata") or {}
        title = (page.get("title") or "").replace("File:", "")
        author_html = (meta.get("Artist") or {}).get("value", "") or ""
        author = _strip_html(author_html) or None
        lic = (meta.get("LicenseShortName") or {}).get("value", "") or None
        lic_url = (meta.get("LicenseUrl") or {}).get("value", "") or None
        page_url = f"https://commons.wikimedia.org/wiki/{(page.get('title') or '').replace(' ', '_')}"

        if lic and "fair use" in lic.lower():
            return None, "filtered_license"

        try:
            time.sleep(INTER_REQUEST_SLEEP)
            resp = self._client.get(download_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Wikimedia download failed for %s: %s", download_url, e)
            return None, "download_failed"

        return ImageHit(
            data=resp.content, source="wikimedia",
            source_url=url, page_url=page_url,
            title=title, author=author, license=lic, license_url=lic_url,
        ), None

    def _page_to_hit(self, page: dict) -> Optional[ImageHit]:
        """Converte una page Wikimedia in ImageHit (scaricando il file).
        Ritorna None se il file non e' valido o non scaricabile.
        """
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            return None
        url = info.get("url") or ""
        if not url.lower().endswith(ACCEPTED_EXT):
            return None
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if max(width, height) < MIN_LONG_SIDE:
            return None
        download_url = info.get("thumburl") or url
        meta = info.get("extmetadata") or {}
        title = (page.get("title") or "").replace("File:", "")
        author_html = (meta.get("Artist") or {}).get("value", "") or ""
        author = _strip_html(author_html) or None
        lic = (meta.get("LicenseShortName") or {}).get("value", "") or None
        lic_url = (meta.get("LicenseUrl") or {}).get("value", "") or None
        page_url = f"https://commons.wikimedia.org/wiki/{(page.get('title') or '').replace(' ', '_')}"

        if lic and "fair use" in lic.lower():
            return None

        try:
            time.sleep(INTER_REQUEST_SLEEP)
            resp = self._client.get(download_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Wikimedia download failed for %s: %s", download_url, e)
            return None

        return ImageHit(
            data=resp.content,
            source="wikimedia",
            source_url=url,
            page_url=page_url,
            title=title,
            author=author,
            license=lic,
            license_url=lic_url,
        )

    def search(self, query: str, *, limit: int = 8) -> Optional[ImageHit]:
        """Cerca la prima immagine utile per `query`. Ritorna None se nulla trovato."""
        if not (query or "").strip():
            return None

        # piccolo delay polite tra richieste consecutive
        time.sleep(INTER_REQUEST_SLEEP)
        data = self._api_query({
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,        # File namespace
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlheight": 1350,      # restituisce un thumb di altezza ~1350 dove possibile
        })

        pages = (data.get("query") or {}).get("pages") or []
        for page in pages:
            info = (page.get("imageinfo") or [None])[0]
            if not info:
                continue
            url = info.get("url") or ""
            if not url.lower().endswith(ACCEPTED_EXT):
                continue
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            if max(width, height) < MIN_LONG_SIDE:
                continue
            # Preferisci il thumb se disponibile (piu' leggero del file originale)
            download_url = info.get("thumburl") or url
            meta = info.get("extmetadata") or {}
            title = (page.get("title") or "").replace("File:", "")
            author_html = (meta.get("Artist") or {}).get("value", "") or ""
            # Strip HTML naive
            author = _strip_html(author_html) or None
            lic = (meta.get("LicenseShortName") or {}).get("value", "") or None
            lic_url = (meta.get("LicenseUrl") or {}).get("value", "") or None
            page_url = f"https://commons.wikimedia.org/wiki/{page.get('title','').replace(' ','_')}"

            # Filtra licenze non utilizzabili (alcuni file su Commons sono "fair use" → skip)
            if lic and "fair use" in lic.lower():
                continue

            try:
                resp = self._client.get(download_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("Wikimedia download failed for %s: %s", download_url, e)
                continue

            return ImageHit(
                data=resp.content,
                source="wikimedia",
                source_url=url,
                page_url=page_url,
                title=title,
                author=author,
                license=lic,
                license_url=lic_url,
            )
        return None


def _strip_html(s: str) -> str:
    """Naive HTML strip (i campi Wikimedia author/artist sono HTML)."""
    if not s:
        return ""
    import re
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
