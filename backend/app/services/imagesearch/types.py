"""Tipi condivisi dei provider di image search."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class ImageSearchError(RuntimeError):
    """Errore generico di image search (network, auth, no result)."""


@dataclass
class ImageHit:
    """Una immagine trovata, gia' scaricata e pronta da passare al composer.

    Campi:
    - data: bytes del file immagine (PNG/JPEG).
    - source: "wikimedia" | "unsplash".
    - source_url: URL del file originale (per fallback diretto/debug).
    - page_url: URL della pagina/dell'attribution (per credit nella caption).
    - title: titolo o descrizione breve.
    - author: nome autore (se disponibile).
    - license: nome breve della licenza (es. "CC BY-SA 4.0", "Public Domain", "Unsplash License").
    - license_url: URL della licenza.
    """
    data: bytes
    source: str
    source_url: str
    page_url: str
    title: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    license_url: Optional[str] = None

    def attribution_line(self) -> str:
        """Stringa di credit pronta da incollare nella caption."""
        parts: list[str] = []
        if self.title:
            parts.append(f'"{self.title}"')
        if self.author:
            parts.append(f"by {self.author}")
        if self.license:
            parts.append(f"({self.license})")
        if self.page_url:
            parts.append(self.page_url)
        return " ".join(parts)
