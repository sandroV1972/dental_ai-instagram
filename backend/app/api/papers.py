"""Endpoint /api/papers — ingest, list, dettaglio."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Paper
from ..schemas import PaperBrief, PaperOut
from ..services.ingest import (
    ArxivIngest, PubMedIngest, RssIngest,
    infer_technical_level, score_relevance,
)

router = APIRouter()


@router.get("", response_model=list[PaperBrief])
def list_papers(
    status: Optional[str] = Query(None, description="new/used/skipped"),
    min_score: float = 0.0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    stmt = select(Paper)
    if status:
        stmt = stmt.where(Paper.status == status)
    if min_score > 0:
        stmt = stmt.where(Paper.relevance_score >= min_score)
    stmt = stmt.order_by(desc(Paper.relevance_score), desc(Paper.created_at)).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, "Paper non trovato")
    return p


@router.post("/{paper_id}/status")
def set_paper_status(paper_id: int, status: str, db: Session = Depends(get_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, "Paper non trovato")
    if status not in {"new", "used", "skipped"}:
        raise HTTPException(400, "status deve essere new/used/skipped")
    p.status = status
    db.commit()
    return {"ok": True}


@router.post("/ingest/pubmed")
def ingest_pubmed(retmax: int = 20, db: Session = Depends(get_db)):
    """Trigger manuale di ingest da PubMed (lo scheduler lo richiama anche periodicamente)."""
    ingester = PubMedIngest(
        email=settings.PUBMED_EMAIL,
        api_key=settings.PUBMED_API_KEY,
        query=settings.PUBMED_QUERY,
    )
    try:
        records = ingester.run(retmax=retmax)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Ingest PubMed fallito: {e}")
    inserted = 0
    for r in records:
        if db.execute(select(Paper).where(Paper.source == "pubmed", Paper.external_id == r.pmid)).first():
            continue
        score = score_relevance(title=r.title, abstract=r.abstract, journal=r.journal)
        tech = infer_technical_level(title=r.title, abstract=r.abstract)
        paper = Paper(
            source="pubmed", external_id=r.pmid, pmid=r.pmid, doi=r.doi,
            title=r.title, abstract=r.abstract, journal=r.journal, authors=r.authors,
            url=r.url, published_at=r.published_at,
            relevance_score=score, technical_level=tech,
        )
        db.add(paper)
        inserted += 1
    db.commit()
    return {"fetched": len(records), "inserted": inserted}


@router.post("/ingest/arxiv")
def ingest_arxiv(max_results: int = 15, db: Session = Depends(get_db)):
    ingester = ArxivIngest()
    try:
        records = ingester.run(max_results=max_results)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Ingest arXiv fallito: {e}")
    inserted = 0
    for r in records:
        if db.execute(select(Paper).where(Paper.source == "arxiv", Paper.external_id == r.arxiv_id)).first():
            continue
        score = score_relevance(title=r.title, abstract=r.abstract, journal="arXiv")
        tech = infer_technical_level(title=r.title, abstract=r.abstract)
        paper = Paper(
            source="arxiv", external_id=r.arxiv_id,
            title=r.title, abstract=r.abstract, journal="arXiv",
            authors=r.authors, url=r.url, published_at=r.published_at,
            relevance_score=score, technical_level=tech,
        )
        db.add(paper)
        inserted += 1
    db.commit()
    return {"fetched": len(records), "inserted": inserted}


@router.post("/ingest/rss")
def ingest_rss(db: Session = Depends(get_db)):
    ingester = RssIngest()
    try:
        records = ingester.run()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Ingest RSS fallito: {e}")
    inserted = 0
    for r in records:
        if db.execute(select(Paper).where(Paper.source == "rss", Paper.external_id == r.feed_id)).first():
            continue
        score = score_relevance(title=r.title, abstract=r.summary, journal=None)
        tech = infer_technical_level(title=r.title, abstract=r.summary)
        paper = Paper(
            source="rss", external_id=r.feed_id, title=r.title, abstract=r.summary,
            url=r.url, published_at=r.published_at,
            relevance_score=score, technical_level=tech,
        )
        db.add(paper)
        inserted += 1
    db.commit()
    return {"fetched": len(records), "inserted": inserted}
