"""Pollinations.ai — image generation FREE, no auth, no rate limits.

Docs: https://github.com/pollinations/pollinations/blob/master/APIDOCS.md
Endpoint: GET https://image.pollinations.ai/prompt/{prompt}?width=...&height=...&model=...

Modelli supportati (al 2026-05):
- flux         — il principale (FLUX.1 schnell), buona qualita' generale
- flux-realism — fotorealismo
- flux-anime   — stile anime (non utile per noi)
- turbo        — piu' veloce ma meno qualita'

Per il nostro use case (medical/scientific aesthetic) "flux" o "flux-realism"
sono ottimi candidati. Lo style suffix vincola comunque l'estetica.
"""
from __future__ import annotations

import logging
import random
import urllib.parse
from typing import Optional

import httpx

from .base_image import BaseImageProvider, ImageGenError

logger = logging.getLogger(__name__)


BASE_URL = "https://image.pollinations.ai/prompt"

STYLE_SUFFIX = (
    " — clean minimalist editorial photography, soft natural lighting, "
    "muted desaturated palette with subtle teal and slate tones, "
    "medical-technology aesthetic, no text, no logos, no watermarks, "
    "shallow depth of field, premium magazine quality, ultra-realistic"
)


def _dims_for_ratio(aspect_ratio: str) -> tuple[int, int]:
    # Pollinations preferisce dimensioni multiple di 64 e <= 1280 per il free tier
    if aspect_ratio == "1:1":
        return 1024, 1024
    if aspect_ratio == "9:16":
        return 768, 1280
    if aspect_ratio == "16:9":
        return 1280, 768
    # 3:4 (default per carousel)
    return 960, 1280


class PollinationsProvider(BaseImageProvider):
    name = "pollinations"

    def __init__(self, model: str = "flux"):
        self.model = model

    def generate(self, *, visual_hint: str, is_cover: bool = False,
                 aspect_ratio: str = "3:4") -> bytes:
        prompt = self._build_prompt(visual_hint, is_cover)
        w, h = _dims_for_ratio(aspect_ratio)
        # seed casuale per ottenere immagini diverse a ogni chiamata (utile per le 3 varianti)
        seed = random.randint(1, 9_999_999)
        params = {
            "width": w, "height": h,
            "model": self.model,
            "nologo": "true",
            "enhance": "true",
            "seed": str(seed),
        }
        # path-encoded prompt
        encoded_prompt = urllib.parse.quote(prompt, safe="")
        url = f"{BASE_URL}/{encoded_prompt}"
        try:
            # Pollinations puo' essere lento (10-40s per generazione)
            r = httpx.get(url, params=params, timeout=120.0, follow_redirects=True)
        except httpx.HTTPError as e:
            raise ImageGenError(f"Pollinations request failed: {e}") from e
        if r.status_code != 200:
            raise ImageGenError(f"Pollinations HTTP {r.status_code}: {r.text[:200]}")
        if not r.content or len(r.content) < 1000:
            raise ImageGenError("Pollinations ha restituito un payload vuoto/troppo piccolo")
        # Content-Type dovrebbe essere image/jpeg o image/png; lo accettiamo entrambi
        return r.content

    def _build_prompt(self, visual_hint: str, is_cover: bool) -> str:
        base = (visual_hint or "").strip()
        if not base:
            base = "abstract clean composition representing scientific innovation in dentistry"
        framing = (
            "portrait orientation, centered subject" if is_cover
            else "portrait orientation, environmental context, "
                 "clean negative space in lower half for overlay text"
        )
        return f"{base}{STYLE_SUFFIX}. {framing}."
