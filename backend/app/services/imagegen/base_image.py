"""Astrazione comune per provider di image generation (Imagen, Gemini Image, ...)."""
from __future__ import annotations


class ImageGenError(RuntimeError):
    """Errore generico di un provider di image generation."""


class BaseImageProvider:
    """Interfaccia di base. Tutti i provider devono esporre `generate(...)`."""

    name = "base"

    def generate(self, *, visual_hint: str, is_cover: bool = False,
                 aspect_ratio: str = "3:4") -> bytes:
        raise NotImplementedError
