"""Ingest da PubMed via NCBI E-utilities.

ESearch -> lista PMID -> ESummary/EFetch -> metadati. Documentazione:
https://www.ncbi.nlm.nih.gov/books/NBK25501/

Si rispetta il rate limit (3 req/s senza API key, 10 con key) inserendo
piccoli sleep tra le chiamate.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubMedRecord:
    pmid: str
    title: str
    abstract: Optional[str]
    journal: Optional[str]
    authors: Optional[str]
    doi: Optional[str]
    published_at: Optional[datetime]
    url: str


class PubMedIngest:
    def __init__(self, email: str, api_key: Optional[str] = None, query: str = ""):
        self.email = email
        self.api_key = api_key
        self.query = query
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _common_params(self) -> dict:
        p = {"tool": "dental-ai-content", "email": self.email}
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    def _sleep(self) -> None:
        time.sleep(0.12 if self.api_key else 0.34)

    def search(self, *, query: Optional[str] = None, retmax: int = 20) -> list[str]:
        q = query or self.query
        if not q:
            return []
        params = {**self._common_params(), "db": "pubmed", "term": q, "retmax": retmax, "sort": "date"}
        r = httpx.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=self._timeout)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ids = [el.text for el in root.findall(".//IdList/Id") if el.text]
        self._sleep()
        return ids

    def fetch(self, pmids: list[str]) -> list[PubMedRecord]:
        if not pmids:
            return []
        params = {**self._common_params(), "db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
        r = httpx.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=self._timeout)
        r.raise_for_status()
        self._sleep()
        return list(self._parse(r.text))

    def _parse(self, xml_text: str):
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("PubMed XML parse error: %s", e)
            return
        for art in root.findall(".//PubmedArticle"):
            pmid_el = art.find(".//PMID")
            pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""
            if not pmid:
                continue
            title = "".join((art.find(".//ArticleTitle").itertext())) if art.find(".//ArticleTitle") is not None else ""
            abs_parts = [el.text or "" for el in art.findall(".//Abstract/AbstractText")]
            abstract = " ".join(p.strip() for p in abs_parts if p) or None
            journal_el = art.find(".//Journal/Title")
            journal = (journal_el.text or "").strip() if journal_el is not None else None
            authors_list = []
            for au in art.findall(".//Author"):
                last = au.findtext("LastName") or ""
                init = au.findtext("Initials") or ""
                if last:
                    authors_list.append(f"{last} {init}".strip())
            authors = ", ".join(authors_list) or None

            doi = None
            for aid in art.findall(".//ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text.strip()
                    break

            pub_date = None
            d = art.find(".//PubDate")
            if d is not None:
                year = d.findtext("Year")
                month = d.findtext("Month") or "1"
                day = d.findtext("Day") or "1"
                try:
                    # 'Jan' -> 1, etc.
                    if month.isalpha():
                        month = str(datetime.strptime(month[:3], "%b").month)
                    pub_date = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pub_date = None

            yield PubMedRecord(
                pmid=pmid,
                title=title.strip(),
                abstract=abstract,
                journal=journal,
                authors=authors,
                doi=doi,
                published_at=pub_date,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            )

    def run(self, *, retmax: int = 20) -> list[PubMedRecord]:
        ids = self.search(retmax=retmax)
        return self.fetch(ids)
