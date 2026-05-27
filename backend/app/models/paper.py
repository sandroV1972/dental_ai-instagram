from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Float, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Paper(Base):
    """Paper/articolo raccolto da PubMed/arXiv/RSS."""

    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_paper_source_ext"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # pubmed, arxiv, rss
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    doi: Mapped[Optional[str]] = mapped_column(String(256), index=True, nullable=True)
    pmid: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    relevance_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    technical_level: Mapped[str] = mapped_column(String(16), default="medium", server_default="medium")
    status: Mapped[str] = mapped_column(String(24), default="new", server_default="new")  # new, used, skipped

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contents = relationship("Content", back_populates="paper")
