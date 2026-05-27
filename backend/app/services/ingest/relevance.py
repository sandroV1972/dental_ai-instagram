"""Scoring di rilevanza e livello tecnico per i paper raccolti.

Regole semplici, deterministiche, no LLM (cosi' rimane economico e
spiegabile). Lo score e' una somma pesata di matches keyword + bonus per
journal noti odontoiatrici.
"""
from __future__ import annotations

import re
from typing import Iterable

DENTAL_KEYWORDS = [
    "dental", "dentistry", "odontolog", "oral health", "tooth", "teeth",
    "orthodont", "endodont", "periodont", "prosthodont", "implant",
    "caries", "panoramic", "cephalometr", "bitewing", "cbct",
    "intraoral", "occlus", "malocclus", "invisalign", "aligner",
]
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "convolutional", "transformer", "computer vision",
    "u-net", "yolo", "segmentation", "classification", "detection",
]
EVIDENCE_KEYWORDS = [
    "systematic review", "meta-analysis", "randomized controlled trial",
    "rct", "prospective study", "cohort study", "cross-sectional",
]
RED_FLAGS = [
    # claim sensazionalistici nelle abstract → meno preferibili come fonte
    "replace the dentist", "replaces dentists", "100% accuracy",
]

JOURNAL_BONUSES = {
    "nature": 3.0,
    "lancet": 3.0,
    "jada": 2.5,
    "journal of dental research": 3.0,
    "clinical oral implants research": 2.0,
    "dental materials": 2.0,
    "european journal of orthodontics": 2.0,
    "international endodontic journal": 2.0,
    "journal of periodontology": 2.0,
    "oral surgery oral medicine oral pathology": 2.0,
    "arxiv": 0.5,
}


def _count_matches(text: str, kws: Iterable[str]) -> int:
    if not text:
        return 0
    t = text.lower()
    return sum(1 for k in kws if k in t)


def score_relevance(*, title: str, abstract: str | None, journal: str | None) -> float:
    """Score 0..10, dove >=6 = molto rilevante, 3..6 = forse rilevante, <3 = scartare.

    Pesi: dental match doppio rispetto a AI (la specificita' odontoiatrica e' piu' rara).
    Evidence-based keywords danno bonus. Red flags penalizzano.
    """
    full = " ".join(filter(None, [title or "", abstract or ""]))
    dental = _count_matches(full, DENTAL_KEYWORDS)
    ai = _count_matches(full, AI_KEYWORDS)
    evidence = _count_matches(full, EVIDENCE_KEYWORDS)
    red = _count_matches(full, RED_FLAGS)

    score = (2.0 * min(dental, 4)) + (1.2 * min(ai, 4)) + (0.8 * min(evidence, 3))
    score -= 2.0 * red

    if journal:
        jl = journal.lower()
        for key, bonus in JOURNAL_BONUSES.items():
            if key in jl:
                score += bonus
                break

    if dental == 0 or ai == 0:
        # senza dental+AI insieme, taglia drasticamente
        score *= 0.4

    return max(0.0, min(10.0, round(score, 2)))


def infer_technical_level(*, title: str, abstract: str | None) -> str:
    """low/medium/high in base alla densita' di termini tecnici/statistici."""
    full = (title or "") + " " + (abstract or "")
    t = full.lower()
    tech_signals = sum(
        1 for k in (
            "convolutional", "transformer", "yolo", "u-net", "auc", "roc",
            "p<0.0", "kappa", "dice coefficient", "iou", "feature map",
            "backbone", "pre-trained", "hyperparameter", "ensemble",
        ) if k in t
    )
    if tech_signals >= 4:
        return "high"
    if tech_signals >= 2:
        return "medium"
    if re.search(r"\bclinical\b|\bpatients?\b|\bworkflow\b", t):
        return "low"
    return "medium"
