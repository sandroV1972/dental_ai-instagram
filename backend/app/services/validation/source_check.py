"""Verifica esistenza fonti scientifiche citate.

- DOI: lookup su CrossRef (api.crossref.org/works/<doi>)
- PMID: lookup su NCBI E-utilities (esummary db=pubmed)

Se la fonte non esiste, il contenuto va bloccato dalla pubblicazione.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
PMID_RE = re.compile(r"\bPMID[:\s]*([0-9]{4,9})\b", re.IGNORECASE)


@dataclass
class SourceCheckResult:
    kind: str        # "doi" | "pmid"
    identifier: str
    verified: bool
    title: Optional[str] = None
    message: Optional[str] = None


def _check_doi(doi: str) -> SourceCheckResult:
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = httpx.get(url, timeout=15.0, headers={"User-Agent": "dental-ai-content/0.1 (mailto:dev@example.com)"})
    except httpx.HTTPError as e:
        return SourceCheckResult("doi", doi, False, message=f"CrossRef unreachable: {e}")
    if r.status_code == 404:
        return SourceCheckResult("doi", doi, False, message="DOI non trovato in CrossRef")
    if r.status_code != 200:
        return SourceCheckResult("doi", doi, False, message=f"CrossRef HTTP {r.status_code}")
    try:
        data = r.json().get("message") or {}
        title = (data.get("title") or [None])[0]
        return SourceCheckResult("doi", doi, True, title=title)
    except ValueError:
        return SourceCheckResult("doi", doi, False, message="Risposta CrossRef non JSON")


def _check_pmid(pmid: str) -> SourceCheckResult:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    try:
        r = httpx.get(url, params=params, timeout=15.0)
    except httpx.HTTPError as e:
        return SourceCheckResult("pmid", pmid, False, message=f"PubMed unreachable: {e}")
    if r.status_code != 200:
        return SourceCheckResult("pmid", pmid, False, message=f"PubMed HTTP {r.status_code}")
    try:
        data = r.json()
        result = (data.get("result") or {}).get(pmid) or {}
        if not result or result.get("error"):
            return SourceCheckResult("pmid", pmid, False, message="PMID non trovato")
        return SourceCheckResult("pmid", pmid, True, title=result.get("title"))
    except ValueError:
        return SourceCheckResult("pmid", pmid, False, message="Risposta PubMed non JSON")


def verify_source(kind: str, identifier: str) -> SourceCheckResult:
    kind_l = kind.lower()
    if kind_l == "doi":
        return _check_doi(identifier)
    if kind_l == "pmid":
        return _check_pmid(identifier)
    return SourceCheckResult(kind, identifier, False, message=f"Kind non supportato: {kind}")


def verify_sources_in_text(text: str) -> list[SourceCheckResult]:
    """Estrae automaticamente DOI/PMID da un testo (caption, slide, script) e li verifica."""
    out: list[SourceCheckResult] = []
    seen: set[tuple[str, str]] = set()
    for m in DOI_RE.finditer(text or ""):
        doi = m.group(0).rstrip(".,;)")
        key = ("doi", doi.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(_check_doi(doi))
    for m in PMID_RE.finditer(text or ""):
        pmid = m.group(1)
        key = ("pmid", pmid)
        if key in seen:
            continue
        seen.add(key)
        out.append(_check_pmid(pmid))
    return out
