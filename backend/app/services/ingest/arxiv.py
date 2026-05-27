"""Ingest da arXiv via API Atom (http://export.arxiv.org/api/query)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}


@dataclass
class ArxivRecord:
    arxiv_id: str
    title: str
    abstract: Optional[str]
    authors: Optional[str]
    published_at: Optional[datetime]
    url: str


class ArxivIngest:
    def __init__(self, query: str = "abs:dental AND (abs:deep+learning OR abs:machine+learning)"):
        self.query = query

    def run(self, max_results: int = 15) -> list[ArxivRecord]:
        params = {
            "search_query": self.query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        }
        try:
            r = httpx.get(ARXIV_API, params=params, timeout=30.0)
            r.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("arXiv request failed: %s", e)
            return []
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as e:
            logger.warning("arXiv XML parse error: %s", e)
            return []
        out: list[ArxivRecord] = []
        for entry in root.findall("a:entry", NS):
            id_el = entry.find("a:id", NS)
            if id_el is None or not id_el.text:
                continue
            full_id = id_el.text.strip()
            arxiv_id = full_id.rsplit("/", 1)[-1]
            title_el = entry.find("a:title", NS)
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            sum_el = entry.find("a:summary", NS)
            abstract = (sum_el.text or "").strip() if sum_el is not None else None
            authors = ", ".join(
                (a.findtext("a:name", default="", namespaces=NS) or "").strip()
                for a in entry.findall("a:author", NS)
            ) or None
            pub_el = entry.find("a:published", NS)
            published_at = None
            if pub_el is not None and pub_el.text:
                try:
                    published_at = datetime.fromisoformat(pub_el.text.replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
            out.append(ArxivRecord(
                arxiv_id=arxiv_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published_at=published_at,
                url=full_id,
            ))
        return out
