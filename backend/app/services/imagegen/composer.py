"""Composer Pillow — stile dark editorial Instagram 2026.

Layout (carousel 1080x1350, theme dark):

  ┌─────────────────────────────────────────┐
  │ ━━━━━                            03/06  │  header: accent + handle/slide#
  │ @dr.valenti                             │
  │                                         │
  │                                         │
  │    03                                   │  ← big number indicator (solo content)
  │   ━━━                                   │
  │                                         │
  │   How CNN segmentation                  │  ← title BIG bold
  │   supports the clinician                │
  │                                         │
  │   ─────                                 │
  │   Convolutional networks identify       │  ← body
  │   patterns in panoramic radiographs     │
  │   supporting the dentist's judgement.   │
  │                                         │
  │                                         │
  │      ●●○○○○                              │  ← progress dots
  │      Dr. Valenti × AI                   │
  └─────────────────────────────────────────┘

Cover (is_cover=True): niente number indicator, titolo MAXI (110pt), hook in accent.
CTA (is_cta=True): titolo grande + CTA in accent color, layout centrato.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .palette import CANVAS, PALETTE


# --- Caricamento font (sistema o fallback) -------------------------------

_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans[wdth,wght].ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _resolve_font(candidates: list[str]) -> Optional[str]:
    for p in candidates:
        if Path(p).exists():
            return p
    return None


_FONT_REGULAR = _resolve_font(_FONT_CANDIDATES_REGULAR)
_FONT_BOLD = _resolve_font(_FONT_CANDIDATES_BOLD)


def _load_font(*, bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REGULAR
    if not path:
        return ImageFont.load_default()
    return ImageFont.truetype(path, size=size)


# --- Word wrapping con misure reali del font -----------------------------

def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text:
        return []
    words = text.replace("\n", " ").split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        candidate = " ".join(cur + [word])
        bbox = font.getbbox(candidate)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
                cur = [word]
            else:
                lines.append(word)
                cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines


def _draw_text_block(draw: ImageDraw.ImageDraw, lines: list[str], *,
                     font: ImageFont.FreeTypeFont, x: int, y: int,
                     line_spacing: float, color) -> int:
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * line_spacing)
    for line in lines:
        draw.text((x, y), line, fill=color, font=font)
        y += line_h
    return y


# --- Background composition ----------------------------------------------

def _solid_dark_background(size: tuple[int, int]) -> Image.Image:
    """Sfondo dark navy con leggera vignette ai bordi (premium look)."""
    W, H = size
    img = Image.new("RGB", (W, H), PALETTE["bg"])
    # Sottile gradient verticale: piu' scuro al centro orizzontale, piu' chiaro ai bordi
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Halo centrale (leggermente piu' chiaro)
    cx, cy = W // 2, H // 2
    max_r = int(((W ** 2 + H ** 2) ** 0.5) / 1.6)
    # Disegno cerchi concentrici dal centro per simulare un radial gradient
    # 24 step, alpha che decresce dal centro
    for i, r in enumerate(range(0, max_r, max_r // 24)):
        alpha = max(0, 12 - i // 2)  # halo leggerissimo
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(56, 189, 248, alpha))  # sky tint
    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return out


def _prepare_background(canvas_size: tuple[int, int],
                        background_image: Optional[bytes]) -> tuple[Image.Image, bool]:
    """Ritorna (image, has_ai_bg). Se viene fornita una immagine AI/CC, la usa con
    overlay scuro per leggibilita'. Altrimenti sfondo dark navy con vignette.
    """
    W, H = canvas_size
    if not background_image:
        return _solid_dark_background((W, H)), False

    try:
        src = Image.open(BytesIO(background_image)).convert("RGB")
    except Exception:  # noqa: BLE001
        return _solid_dark_background((W, H)), False

    # cover-crop al canvas
    src_w, src_h = src.size
    scale = max(W / src_w, H / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    src = src.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - W) // 2
    top = (new_h - H) // 2
    img = src.crop((left, top, left + W, top + H))

    # Overlay scuro graduato: piu' scuro dove finisce il testo (basso 60%)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_o = ImageDraw.Draw(overlay)
    # Uniforme leggera su tutto (per coerenza brand)
    draw_o.rectangle([0, 0, W, H], fill=(15, 23, 42, 70))
    # Gradient sul 60% inferiore: alpha 70 → 200
    grad_start = int(H * 0.40)
    for y in range(grad_start, H):
        t = (y - grad_start) / max(1, H - grad_start)
        alpha = int(70 + (180 - 70) * t)
        draw_o.line([(0, y), (W, y)], fill=(15, 23, 42, alpha))

    base = img.convert("RGBA")
    composed = Image.alpha_composite(base, overlay).convert("RGB")
    return composed, True


# --- Decorative helpers --------------------------------------------------

def _draw_progress_dots(draw: ImageDraw.ImageDraw, *, w: int, y: int,
                        current: int, total: int,
                        filled, empty, radius: int = 5, spacing: int = 18):
    if total < 1:
        return
    total_w = (total - 1) * spacing + 2 * radius
    x_start = (w - total_w) // 2
    for i in range(total):
        cx = x_start + i * spacing + radius
        color = filled if i < current else empty
        draw.ellipse([cx - radius, y - radius, cx + radius, y + radius], fill=color)


def _draw_accent_strip(draw, x, y, w=96, h=6, color=None):
    color = color or PALETTE["accent"]
    draw.rectangle([x, y, x + w, y + h], fill=color)


# --- API pubblica --------------------------------------------------------

def render_slide(
    *,
    canvas: str = "carousel",
    title: str,
    body: str = "",
    slide_index: int = 1,
    slide_total: int = 1,
    author_name: str = "",
    handle: str = "",
    tagline: str = "",
    background_image: Optional[bytes] = None,
    is_cover: bool = False,
    is_cta: bool = False,
) -> bytes:
    """Renderizza una slide PNG in dark editorial style.

    Layout adattivo:
    - is_cover=True  → niente number indicator, titolo MAXI, hook in accent
    - is_cta=True    → body in accent color (call-to-action evidenziata)
    - default        → big number indicator + titolo bold + body
    """
    if canvas not in CANVAS:
        raise ValueError(f"canvas non valido: {canvas!r}. Valori: {list(CANVAS)}")
    W, H = CANVAS[canvas]
    img, has_ai_bg = _prepare_background((W, H), background_image)
    draw = ImageDraw.Draw(img)

    margin = 90
    inner_w = W - 2 * margin

    # Colori (gli stessi su dark navy e su AI bg con overlay)
    c_accent = PALETTE["accent"]
    c_accent_bright = PALETTE["accent_bright"]
    c_header = PALETTE["ink_muted"]
    c_title = PALETTE["ink"]
    c_body = PALETTE["ink_soft"]
    c_footer = PALETTE["ink_muted"]
    c_dot_filled = PALETTE["accent"]
    c_dot_empty = PALETTE["ink_faint"]

    # --- Header (top): accent strip + handle a sinistra, slide# a destra ---
    accent_top = 80
    _draw_accent_strip(draw, margin, accent_top, w=64, h=5, color=c_accent)
    f_meta = _load_font(bold=False, size=26)
    if handle:
        draw.text((margin, accent_top + 22), handle, fill=c_header, font=f_meta)
    if slide_total > 1:
        snum = f"{slide_index:02d} / {slide_total:02d}"
        bb = f_meta.getbbox(snum)
        snum_w = bb[2] - bb[0]
        draw.text((W - margin - snum_w, accent_top + 22), snum, fill=c_header, font=f_meta)

    # --- Number indicator (solo content slides, non cover/cta) ---
    # Posizionato in alto a sinistra del blocco testo
    number_y_offset = 0
    if not is_cover and not is_cta and slide_total > 1:
        f_num = _load_font(bold=True, size=120)
        num_txt = f"{slide_index:02d}"
        # Disegno il numero in slate-700 (subdued, decorativo)
        draw.text((margin, accent_top + 80), num_txt,
                  fill=PALETTE["rule"] if not has_ai_bg else (51, 65, 85), font=f_num)
        # Linea sotto al numero
        _draw_accent_strip(draw, margin, accent_top + 80 + 130, w=80, h=4, color=c_accent)
        number_y_offset = 250  # spazio occupato

    # --- Title (BIG bold) ---
    if is_cover:
        title_size = 108
    elif canvas == "story" or canvas == "reel_cover":
        title_size = 92
    else:
        title_size = 72
    f_title = _load_font(bold=True, size=title_size)
    title_lines = _wrap(title or "", f_title, inner_w)
    title_lines = title_lines[:5 if is_cover else 4]

    # --- Body / hook ---
    if is_cover:
        body_size = 44
    elif is_cta:
        body_size = 56
    else:
        body_size = 38
    f_body = _load_font(bold=False, size=body_size)
    body_lines = _wrap(body or "", f_body, inner_w) if body else []
    body_lines = body_lines[:3 if is_cover else (3 if is_cta else 8)]

    # Misure
    a_t, d_t = f_title.getmetrics()
    a_b, d_b = f_body.getmetrics()
    line_h_title = int((a_t + d_t) * 1.05)
    line_h_body = int((a_b + d_b) * 1.45)
    title_h = len(title_lines) * line_h_title
    body_h = len(body_lines) * line_h_body
    gap = 50 if body_lines else 0
    block_h = title_h + gap + body_h

    # Layout verticale
    footer_y_top = H - 200  # spazio riservato al footer
    block_top_y_max = footer_y_top - block_h - 30

    if is_cover:
        # Cover: titolo centrato verticalmente, niente number indicator
        y_start = max(accent_top + 130, (H - block_h) // 2)
    elif is_cta:
        # CTA: centrato verticalmente, leggermente sopra
        y_start = max(accent_top + 130, (H - block_h) // 2 - 40)
    else:
        # Content: subito sotto al number indicator
        y_start = accent_top + 80 + number_y_offset
        # Ma non oltre il footer area
        if y_start + block_h > footer_y_top - 40:
            y_start = max(accent_top + 130, footer_y_top - block_h - 40)

    # Disegna titolo
    y = _draw_text_block(draw, title_lines, font=f_title, x=margin, y=y_start,
                        line_spacing=1.05, color=c_title)
    # Separatore sottile fra titolo e body (solo se body presente)
    if body_lines:
        sep_y = y + 12
        if not is_cta:
            draw.rectangle([margin, sep_y, margin + 60, sep_y + 3], fill=c_accent)
            y += gap
        else:
            y += gap // 2

    # Disegna body — su CTA usa accent color per emphasis
    body_color = c_accent_bright if is_cta else c_body
    _draw_text_block(draw, body_lines, font=f_body, x=margin, y=y,
                    line_spacing=1.45, color=body_color)

    # --- Footer: progress dots + brand tagline ---
    dots_y = H - 130
    if slide_total > 1:
        _draw_progress_dots(draw, w=W, y=dots_y, current=slide_index, total=slide_total,
                           filled=c_dot_filled, empty=c_dot_empty)

    f_footer = _load_font(bold=False, size=24)
    footer_parts = []
    if author_name:
        footer_parts.append(author_name)
    if tagline:
        footer_parts.append(tagline)
    footer_text = "  ·  ".join(footer_parts)
    if footer_text:
        bb = f_footer.getbbox(footer_text)
        ftw = bb[2] - bb[0]
        draw.text(((W - ftw) // 2, H - 90), footer_text, fill=c_footer, font=f_footer)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
