from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Source(Base):
    """Citazione/fonte verificabile associata a un Content."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))  # doi, pmid, url
    identifier: Mapped[str] = mapped_column(String(256))
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verification_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    content = relationship("Content", back_populates="sources")
