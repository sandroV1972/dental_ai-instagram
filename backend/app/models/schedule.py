from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class ScheduleSlot(Base):
    """Slot del calendario editoriale per un Content."""

    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"))
    slot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(32), default="instagram", server_default="instagram")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    content = relationship("Content", back_populates="schedule_slots")
