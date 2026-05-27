"""Palette colori e dimensioni canvas per il rendering delle slide.

Stile: dark editorial bold (Instagram 2026 vibe).
Sfondo navy scuro, tipografia bianca + accent sky-blue, contrasto alto,
type molto grande, progress dots, number indicator.
"""

# Tutti i colori sono RGB tuple (Pillow-friendly).
PALETTE = {
    # Sfondi (dark theme)
    "bg":            (15, 23, 42),       # slate-900 — fondo principale
    "bg_alt":        (30, 41, 59),       # slate-800 — variazione per gradient sottile
    "bg_card":       (255, 255, 255),    # bianco per slide "light variant" (se mai serve)
    # Testo
    "ink":           (255, 255, 255),    # bianco — titolo principale
    "ink_soft":      (226, 232, 240),    # slate-200 — body
    "ink_muted":     (148, 163, 184),    # slate-400 — meta (handle, slide#, footer)
    "ink_faint":     (71, 85, 105),      # slate-600 — dots non attivi
    # Accent
    "accent":        (56, 189, 248),     # sky-400 — accent principale (line, CTA)
    "accent_bright": (125, 211, 252),    # sky-300 — accent luminoso (hook su scuro)
    "accent_deep":   (3, 105, 161),      # sky-700 — accent scuro
    # Decorazioni
    "rule":          (51, 65, 85),       # slate-700 — linee divisorie
    # Legacy keys (compat con vecchio composer, niente piu' usato attivamente)
    "bg_top":        (15, 23, 42),
    "bg_bot":        (30, 41, 59),
    "accent_dark":   (3, 105, 161),
}

# Dimensioni canvas per i vari formati Instagram.
CANVAS = {
    "carousel":   (1080, 1350),  # 4:5, formato consigliato per carousel
    "post":       (1080, 1080),  # 1:1, post singolo classico
    "reel_cover": (1080, 1920),  # 9:16, frame video reel
    "story":      (1080, 1920),  # 9:16, Instagram Story
}
