"""Regole deterministiche di validazione contenuti.

Indipendenti dall'AI, eseguite ad ogni generazione/salvataggio. Producono
una lista di issues con severita' error/warning/info.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ...core.config import settings

# Pattern di sensazionalismo/claim assoluti — bilingue (IT + EN).
# Case-insensitive. Pensati per match specifici, no falsi positivi su prosa cauta.
ABSOLUTE_CLAIM_PATTERNS = [
    # --- Italiano ---
    r"\bsostituisc[ei]\b(?!\s+il\s+(?:supporto|software))",
    r"\brimpiazz[a-z]+\s+(?:il|i)\s+dentist",
    r"\bAI\s+sostituir[aà]\b",
    r"\bdiagnosi\s+(?:al\s+)?100\s?%",
    r"\bsempre\s+corretta\b",
    r"\bmai\s+sbaglia\b",
    r"\binfallibile\b",
    r"\brivoluzioner[aà]\b",
    r"\bil\s+futuro\s+(?:e[' ]|è)\s+qui\b",
    # --- English ---
    r"\b(?:AI|artificial intelligence)\s+will\s+replace\s+(?:the\s+)?dentists?\b",
    r"\breplaces?\s+(?:the\s+)?dentists?\b",
    r"\b100\s?%\s+accura(?:te|cy)\b",
    r"\bnever\s+wrong\b",
    r"\balways\s+correct\b",
    r"\binfallible\b",
    r"\brevolutioniz(?:es?|ing)\b",
    r"\bgame[\s-]?changer\b",
    r"\bthe\s+future\s+is\s+(?:already\s+)?here\b",
    r"\bdisrupts?\s+dentistry\b",
]
ABSOLUTE_CLAIM_REGEX = re.compile("|".join(ABSOLUTE_CLAIM_PATTERNS), re.IGNORECASE)

# Hint che indicano la presenza del disclaimer clinico (entrambe le lingue).
DISCLAIMER_HINTS = [
    # Italian
    "giudizio clinico", "decisione finale", "ruolo del clinico",
    "supporto al clinico", "supporta il clinico", "supporta il medico",
    "il dentista resta", "il clinico resta",
    # English
    "clinical judgment", "clinical judgement", "final decision",
    "supports the clinician", "supports clinical", "remains central",
    "clinician's judgment", "clinician's judgement",
    "supports the dentist", "the dentist remains", "the clinician remains",
]


@dataclass
class Issue:
    code: str
    severity: str  # error / warning / info
    message: str
    field: str | None = None


@dataclass
class ContentValidation:
    ok: bool
    issues: list[Issue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [issue.__dict__ for issue in self.issues],
        }


def _count_hashtags(s: str) -> int:
    return len(re.findall(r"#\w+", s or ""))


def _has_disclaimer(text: str) -> bool:
    t = (text or "").lower()
    return any(hint in t for hint in DISCLAIMER_HINTS)


def validate_content_rules(*, kind: str, title: str, caption: str, hashtags: str,
                           slides: list[dict] | None = None,
                           reel_script: str | None = None) -> ContentValidation:
    issues: list[Issue] = []

    # --- Lunghezze ---
    if not title or len(title) < 5:
        issues.append(Issue("title_too_short", "error", "Titolo mancante o troppo corto", "title"))
    if len(title) > 255:
        issues.append(Issue("title_too_long", "warning", "Titolo > 255 caratteri", "title"))

    # Story: caption minima molto bassa (overlay breve, niente paragrafi)
    min_caption_chars = 20 if kind == "story" else 50
    if not caption or len(caption.strip()) < min_caption_chars:
        issues.append(Issue(
            "caption_too_short", "error",
            f"Caption mancante o < {min_caption_chars} caratteri", "caption",
        ))
    if len(caption) > settings.CAPTION_MAX_CHARS:
        issues.append(Issue(
            "caption_too_long", "error",
            f"Caption oltre {settings.CAPTION_MAX_CHARS} caratteri (Instagram limit 2200)", "caption",
        ))

    # --- Hashtag ---
    ht_count = _count_hashtags(hashtags) + _count_hashtags(caption)
    if ht_count == 0:
        issues.append(Issue("hashtags_missing", "warning", "Nessun hashtag presente", "hashtags"))
    elif ht_count > settings.HASHTAG_MAX_COUNT:
        issues.append(Issue(
            "hashtags_too_many", "error",
            f"Troppi hashtag ({ht_count}/{settings.HASHTAG_MAX_COUNT})", "hashtags",
        ))

    # --- Claim assoluti / sensazionalismo ---
    full_text = " ".join(filter(None, [title, caption, hashtags, reel_script or ""]))
    for slide in slides or []:
        full_text += " " + " ".join(filter(None, [slide.get("title"), slide.get("body")]))
    for m in ABSOLUTE_CLAIM_REGEX.finditer(full_text):
        issues.append(Issue(
            "absolute_claim", "error",
            f"Trovato claim assoluto/sensazionalistico: \"{m.group(0)}\"", None,
        ))

    # --- Disclaimer clinico ---
    if settings.REQUIRE_CLINICAL_DISCLAIMER and not _has_disclaimer(full_text):
        issues.append(Issue(
            "missing_clinical_disclaimer", "error",
            "Manca riferimento al ruolo centrale del clinico / supporto al medico.", "caption",
        ))

    # --- Vincoli specifici per kind ---
    if kind in ("carousel", "myth_reality", "infographic"):
        n = len(slides or [])
        if n < settings.CAROUSEL_MIN_SLIDES:
            issues.append(Issue(
                "carousel_too_few_slides", "error",
                f"Carousel deve avere almeno {settings.CAROUSEL_MIN_SLIDES} slide (ha {n}).", "slides",
            ))
        if n > settings.CAROUSEL_MAX_SLIDES:
            issues.append(Issue(
                "carousel_too_many_slides", "warning",
                f"Carousel ha {n} slide, Instagram supporta max 10.", "slides",
            ))
        for i, s in enumerate(slides or [], start=1):
            body = (s or {}).get("body") or ""
            if len(body) > 280:
                issues.append(Issue(
                    "slide_body_too_long", "warning",
                    f"Slide {i}: corpo {len(body)} caratteri > 280 (leggibilita' mobile).",
                    f"slides[{i}].body",
                ))
            if not body.strip():
                issues.append(Issue(
                    "slide_body_empty", "error",
                    f"Slide {i}: corpo vuoto.", f"slides[{i}].body",
                ))

    if kind == "reel":
        if not reel_script or len(reel_script.strip()) < 60:
            issues.append(Issue(
                "reel_script_missing", "error",
                "Reel: script mancante o troppo corto (< 60 caratteri).", "reel_script",
            ))
        if reel_script and len(reel_script) > 1200:
            issues.append(Issue(
                "reel_script_too_long", "warning",
                "Reel script > 1200 caratteri (probabile durata >45s).", "reel_script",
            ))

    ok = not any(i.severity == "error" for i in issues)
    return ContentValidation(ok=ok, issues=issues)
