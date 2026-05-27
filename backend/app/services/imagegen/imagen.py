"""Provider di image generation via Google Imagen / Gemini AI Studio.

Uso l'SDK `google-generativeai` (gia' presente nei requirements). Imagen e'
disponibile via models.generate_images sull'endpoint v1beta. Documentazione:
https://ai.google.dev/gemini-api/docs/image-generation

Per ora supporto solo Imagen 3 / 4. Lo stile viene "forzato" dal prompt
con un suffisso che vincola estetica medical-tech minimal.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from .base_image import BaseImageProvider, ImageGenError

# Alias di compatibilita' con il vecchio nome
ImagenError = ImageGenError

logger = logging.getLogger(__name__)


# Suffisso di stile applicato a ogni prompt → coerenza estetica del feed.
STYLE_SUFFIX = (
    " — clean minimalist editorial photography, soft natural lighting, "
    "muted desaturated palette with subtle teal and slate tones, "
    "medical-technology aesthetic, no text, no logos, no watermarks, "
    "shallow depth of field, premium magazine quality, ultra-realistic, 4k"
)

NEGATIVE_HINTS = (
    "no text, no captions, no typography, no watermark, no signature, "
    "no logos, no UI elements, no charts, no infographic style, "
    "no neon, no cyberpunk, no hands with extra fingers"
)


def _enrich_prompt(visual_hint: str, *, is_cover: bool) -> str:
    """Combina visual_hint dell'AI con il suffisso di stile e i negative hints."""
    base = (visual_hint or "").strip()
    if not base:
        base = "abstract clean composition representing scientific innovation in dentistry"
    framing = (
        "portrait orientation 4:5, centered subject" if is_cover
        else "portrait orientation 4:5, environmental context, leaves clean negative space in lower half for overlay text"
    )
    return f"{base}{STYLE_SUFFIX}. {framing}. {NEGATIVE_HINTS}."


class ImagenProvider(BaseImageProvider):
    """Generatore di sfondi via Google Imagen 3 (REST API v1beta).

    Si usa l'endpoint
        POST /v1beta/models/{model}:predict
    con body {"instances":[{"prompt": "..."}], "parameters": {...}}.
    """

    def __init__(self, api_key: Optional[str], model: str):
        if not api_key:
            raise ImagenError("GOOGLE_API_KEY non configurata: image generation disabilitato")
        self.api_key = api_key
        self.model = model

    def generate(self, *, visual_hint: str, is_cover: bool = False,
                 aspect_ratio: str = "3:4") -> bytes:
        """Genera un'immagine PNG bytes. Solleva ImagenError se il provider fallisce
        (no credit, modello non disponibile, safety filter, ecc.)."""
        prompt = _enrich_prompt(visual_hint, is_cover=is_cover)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:predict?key={self.api_key}"
        )
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": aspect_ratio,
                "personGeneration": "allow_adult",
                "safetyFilterLevel": "block_only_high",
            },
        }
        try:
            r = httpx.post(url, json=payload, timeout=60.0)
        except httpx.HTTPError as e:
            raise ImagenError(f"Imagen request failed: {e}") from e

        if r.status_code != 200:
            # 400/403/404 da Google contengono utile messaggio in JSON
            try:
                err = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                err = r.text
            raise ImagenError(f"Imagen HTTP {r.status_code}: {err}")

        try:
            data = r.json()
        except ValueError as e:
            raise ImagenError(f"Imagen risposta non JSON: {e}") from e

        # Risposta attesa:
        # { "predictions": [ { "bytesBase64Encoded": "...", "mimeType": "image/png" } ] }
        preds = data.get("predictions") or []
        if not preds:
            # Imagen filtra contenuti potenzialmente problematici e ritorna predictions vuoto
            raise ImagenError(
                "Imagen non ha restituito immagini (probabile filtro safety). "
                "Prova a riformulare visual_hint con termini piu' neutri/clinici."
            )
        b64 = preds[0].get("bytesBase64Encoded")
        if not b64:
            raise ImagenError(f"Imagen risposta priva di bytesBase64Encoded: {preds[0]}")
        try:
            return base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise ImagenError(f"Imagen base64 invalido: {e}") from e
