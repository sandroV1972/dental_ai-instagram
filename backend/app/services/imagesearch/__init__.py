"""Servizi per cercare immagini Creative Commons / stock da usare come sfondo slide.

Due provider:
- WikimediaSearch: public domain + CC. Ottimo per figure storiche, scienza,
  illustrazioni anatomiche. Nessuna API key.
- UnsplashSearch: stock fotografico moderno, alta qualita'. Richiede API key
  gratuita (Unsplash Developer).

Entrambi ritornano `ImageHit` con bytes dell'immagine, attribution, license
e URL sorgente. L'attribution e' importante per la conformita' alle licenze
e va mostrata nella dashboard.
"""
from .types import ImageHit, ImageSearchError
from .wikimedia import WikimediaSearch
from .unsplash import UnsplashSearch

__all__ = ["ImageHit", "ImageSearchError", "WikimediaSearch", "UnsplashSearch"]
