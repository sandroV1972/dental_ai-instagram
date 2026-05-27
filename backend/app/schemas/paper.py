from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaperBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    title: str
    journal: Optional[str] = None
    published_at: Optional[datetime] = None
    relevance_score: float = 0.0
    status: str = "new"


class PaperOut(PaperBrief):
    external_id: str
    doi: Optional[str] = None
    pmid: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    technical_level: str = "medium"
