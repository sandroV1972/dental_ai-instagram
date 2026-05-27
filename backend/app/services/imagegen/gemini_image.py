"""Gemini 2.5 Flash Image (Nano Banana) — image generation via AI Studio free tier.

A differenza di Imagen 3 (che richiede billing), questo modello e' nel free tier
di Google AI Studio. Stesso GOOGLE_API_KEY, endpoint diverso (:generateContent).

API docs: https://ai.google.dev/gemini-api/docs/image-generation
Limiti free tier: 15 richieste/minuto, 1500/giorno (al 2026-05).
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from .base_image import BaseImageProvider, ImageGenError

logger = logging.getLogger(__name__)


STYLE_SUFFIX = (
    " — clean minimalist editorial photography, soft natural lighting, "
    "muted desaturated palette with subtle teal and slate tones, "
    "medical-technology aesthetic, no text, no logos, no watermarks, "
    "shallow depth of field, premium magazine quality, ultra-realistic"
)

NEGATIVE_HINTS = (
    "no text, no captions, no typography, no watermark, no signature, "
    "no logos, no UI elements, no charts, no infographic style, "
    "no neon, no cyberpunk, no hands with extra fingers"
)


class GeminiImageProvider(BaseImageProvider):
    """Generatore via Gemini 2.5 Flash Image (Nano Banana).

    Vantaggi rispetto a Imagen:
    - Free tier accessibile con la stessa GOOGLE_API_KEY
    - Buona qualita' fotografica
    - Aspect ratio specificato implicitamente dal prompt
    """

    name = "gemini_image"

    def __init__(self, api_key: Optional[str], model: str = "gemini-2.5-flash-image"):
        if not api_key:
            raise ImageGenError("GOOGLE_API_KEY non configurata")
        self.api_key = api_key
        self.model = model

    def generate(self, *, visual_hint: str, is_cover: bool = False,
                 aspect_ratio: str = "3:4") -> bytes:
        prompt = self._build_prompt(visual_hint, is_cover, aspect_ratio)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        # Payload minimo conforme alle Gemini Image API docs.
        # NB: il modello di image generation ritorna SEMPRE inlineData PNG,
        # non e' necessario specificare responseModalities (anzi, alcuni
        # endpoint preview lo rifiutano).
        payload = {
            "contents": [{
                "parts": [{"text": prompt}],
            }],
        }
        try:
            r = httpx.post(url, json=payload, timeout=60.0,
                           headers={"Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise ImageGenError(f"Gemini Image request failed: {e}") from e

        # Se il model `gemini-2.5-flash-image` non e' disponibile sull'account,
        # tenta automaticamente con `gemini-2.5-flash-image-preview` (il preview).
        if r.status_code == 404 and "preview" not in self.model:
            preview_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}-preview:generateContent?key={self.api_key}"
            )
            logger.info("Gemini Image: tentativo fallback su %s", preview_url)
            try:
                r = httpx.post(preview_url, json=payload, timeout=60.0,
                               headers={"Content-Type": "application/json"})
            except httpx.HTTPError as e:
                raise ImageGenError(f"Gemini Image (preview) failed: {e}") from e

        if r.status_code != 200:
            try:
                err = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                err = r.text
            raise ImageGenError(f"Gemini Image HTTP {r.status_code}: {err}")

        try:
            data = r.json()
        except ValueError as e:
            raise ImageGenError(f"Gemini Image risposta non JSON: {e}") from e

        # Estrai i bytes dell'immagine dalla prima inlineData utile
        candidates = data.get("candidates") or []
        for cand in candidates:
            parts = ((cand.get("content") or {}).get("parts")) or []
            for p in parts:
                inline = p.get("inlineData") or p.get("inline_data")
                if inline and inline.get("data"):
                    try:
                        return base64.b64decode(inline["data"])
                    except (ValueError, TypeError) as e:
                        raise ImageGenError(f"base64 invalido: {e}") from e

        # Niente immagine → probabile blocco safety o response text-only
        feedback = data.get("promptFeedback") or {}
        block = feedback.get("blockReason") or "no image in response"
        raise ImageGenError(
            f"Gemini Image non ha restituito immagini ({block}). "
            "Prova a riformulare visual_hint con termini piu' neutri/clinici."
        )

    def _build_prompt(self, visual_hint: str, is_cover: bool, aspect_ratio: str) -> str:
        base = (visual_hint or "").strip()
        if not base:
            base = "abstract clean composition representing scientific innovation in dentistry"
        framing = (
            f"portrait orientation aspect ratio {aspect_ratio}, centered subject"
            if is_cover
            else f"portrait orientation aspect ratio {aspect_ratio}, environmental context, "
                 "leaves clean negative space in lower half for overlay text"
        )
        return f"{base}{STYLE_SUFFIX}. {framing}. {NEGATIVE_HINTS}."
