from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Content(Base):
    """Bozza/contenuto Instagram (carousel, reel, post, ecc.)."""

    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[Optional[int]] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))  # carousel, reel, post, infographic, myth_reality, mini_explainer, bts, case_study, paper_commentary

    title: Mapped[str] = mapped_column(String(255))
    hook: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[str] = mapped_column(Text, default="", server_default="")
    cta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    slides_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reel_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    validation_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="draft", server_default="draft")
    # draft, validated, approved, rejected, scheduled, published

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    paper = relationship("Paper", back_populates="contents")
    sources = relationship("Source", back_populates="content", cascade="all, delete-orphan")
    schedule_slots = relationship("ScheduleSlot", back_populates="content", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="content", cascade="all, delete-orphan")
