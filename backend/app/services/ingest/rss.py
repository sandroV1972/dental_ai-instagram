"""Ingest da feed RSS/Atom generici (es. blog odontoiatrici, news AI medicali)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import feedparser

logger = logging.getLogger(__name__)

# Una manciata di sorgenti ragionevoli; l'utente puo' aggiungere/togliere
DEFAULT_FEEDS = [
    # NewsAggregator scientifici (esempi - sostituire con feed di propria fiducia)
    "https://www.nature.com/subjects/dentistry.rss",
    "https://www.sciencedaily.com/rss/health_medicine/dentistry.xml",
]


@dataclass
class RssRecord:
    feed_id: str
    title: str
    summary: Optional[str]
    url: str
    published_at: Optional[datetime]


class RssIngest:
    def __init__(self, feeds: Optional[Iterable[str]] = None):
        self.feeds = list(feeds or DEFAULT_FEEDS)

    def run(self, max_per_feed: int = 10) -> list[RssRecord]:
        out: list[RssRecord] = []
        for url in self.feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception as e:  # noqa: BLE001
                logger.warning("RSS parse failed for %s: %s", url, e)
                continue
            for entry in (parsed.entries or [])[:max_per_feed]:
                link = entry.get("link") or ""
                if not link:
                    continue
                pub = None
                if entry.get("published_parsed"):
                    pub = datetime(*entry.published_parsed[:6])
                out.append(RssRecord(
                    feed_id=entry.get("id") or link,
                    title=entry.get("title") or "",
                    summary=entry.get("summary"),
                    url=link,
                    published_at=pub,
                ))
        return out
