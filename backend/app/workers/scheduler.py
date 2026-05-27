"""Worker APScheduler: ingest periodico paper PubMed/arXiv/RSS.

Avviato come container separato (`worker` in docker-compose).
"""
from __future__ import annotations

import logging
import signal
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from ..core.config import settings
from ..core.database import SessionLocal
from ..core.logging import setup_logging
from ..models import Paper
from ..services.ingest import (
    ArxivIngest, PubMedIngest, RssIngest,
    infer_technical_level, score_relevance,
)

setup_logging()
logger = logging.getLogger("worker")


def _ingest_pubmed_job():
    logger.info("Job ingest PubMed avviato")
    try:
        ingester = PubMedIngest(
            email=settings.PUBMED_EMAIL,
            api_key=settings.PUBMED_API_KEY,
            query=settings.PUBMED_QUERY,
        )
        records = ingester.run(retmax=settings.INGEST_MAX_PER_RUN)
    except Exception as e:  # noqa: BLE001
        logger.exception("Ingest PubMed fallito: %s", e)
        return
    inserted = 0
    with SessionLocal() as db:
        for r in records:
            if db.execute(select(Paper).where(Paper.source == "pubmed", Paper.external_id == r.pmid)).first():
                continue
            score = score_relevance(title=r.title, abstract=r.abstract, journal=r.journal)
            tech = infer_technical_level(title=r.title, abstract=r.abstract)
            db.add(Paper(
                source="pubmed", external_id=r.pmid, pmid=r.pmid, doi=r.doi,
                title=r.title, abstract=r.abstract, journal=r.journal,
                authors=r.authors, url=r.url, published_at=r.published_at,
                relevance_score=score, technical_level=tech,
            ))
            inserted += 1
        db.commit()
    logger.info("PubMed: fetched=%d inserted=%d", len(records), inserted)


def _ingest_arxiv_job():
    logger.info("Job ingest arXiv avviato")
    try:
        records = ArxivIngest().run(max_results=settings.INGEST_MAX_PER_RUN)
    except Exception as e:  # noqa: BLE001
        logger.exception("Ingest arXiv fallito: %s", e)
        return
    inserted = 0
    with SessionLocal() as db:
        for r in records:
            if db.execute(select(Paper).where(Paper.source == "arxiv", Paper.external_id == r.arxiv_id)).first():
                continue
            score = score_relevance(title=r.title, abstract=r.abstract, journal="arXiv")
            tech = infer_technical_level(title=r.title, abstract=r.abstract)
            db.add(Paper(
                source="arxiv", external_id=r.arxiv_id,
                title=r.title, abstract=r.abstract, journal="arXiv",
                authors=r.authors, url=r.url, published_at=r.published_at,
                relevance_score=score, technical_level=tech,
            ))
            inserted += 1
        db.commit()
    logger.info("arXiv: fetched=%d inserted=%d", len(records), inserted)


def _ingest_rss_job():
    logger.info("Job ingest RSS avviato")
    try:
        records = RssIngest().run()
    except Exception as e:  # noqa: BLE001
        logger.exception("Ingest RSS fallito: %s", e)
        return
    inserted = 0
    with SessionLocal() as db:
        for r in records:
            if db.execute(select(Paper).where(Paper.source == "rss", Paper.external_id == r.feed_id)).first():
                continue
            score = score_relevance(title=r.title, abstract=r.summary, journal=None)
            tech = infer_technical_level(title=r.title, abstract=r.summary)
            db.add(Paper(
                source="rss", external_id=r.feed_id, title=r.title, abstract=r.summary,
                url=r.url, published_at=r.published_at,
                relevance_score=score, technical_level=tech,
            ))
            inserted += 1
        db.commit()
    logger.info("RSS: fetched=%d inserted=%d", len(records), inserted)


def main():
    sched = BlockingScheduler(timezone="UTC")
    hours = max(1, settings.INGEST_INTERVAL_HOURS)
    sched.add_job(_ingest_pubmed_job, "interval", hours=hours, next_run_time=_in_seconds(30))
    sched.add_job(_ingest_arxiv_job, "interval", hours=hours, next_run_time=_in_seconds(60))
    sched.add_job(_ingest_rss_job, "interval", hours=hours, next_run_time=_in_seconds(90))

    def _shutdown(*_):
        logger.info("Shutdown signal received")
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Scheduler avviato (interval=%dh)", hours)
    sched.start()


def _in_seconds(s: int):
    from datetime import datetime, timedelta, timezone as tz
    return datetime.now(tz.utc) + timedelta(seconds=s)


if __name__ == "__main__":
    # piccolo retry connect su DB all'avvio (gestito anche da depends_on healthcheck)
    time.sleep(2)
    main()
