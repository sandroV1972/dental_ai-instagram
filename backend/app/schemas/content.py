from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ContentKind = Literal[
    "carousel",
    "reel",
    "post",
    "story",
    "infographic",
    "myth_reality",
    "mini_explainer",
    "bts",
    "case_study",
    "paper_commentary",
]

Provider = Literal["claude", "openai", "gemini", "deepseek"]


class Slide(BaseModel):
    index: int = Field(ge=1)
    title: str
    body: str
    visual_hint: Optional[str] = None  # suggerimento visuale per l'editor grafico


class GenerationRequest(BaseModel):
    """Request per generare un contenuto.

    - `paper_id` opzionale: se presente, l'AI riceve titolo/abstract come fondamenta.
    - `prompt`: prompt libero dell'utente (puo' essere il solo input se non c'e' paper).
    - `kind`: tipo di contenuto.
    - `provider`: opzionale, default = settings.DEFAULT_AI_PROVIDER.
    - `technical_level`: low/medium/high - regola la complessita' del linguaggio.
    """

    paper_id: Optional[int] = None
    prompt: Optional[str] = None
    kind: ContentKind = "carousel"
    provider: Optional[Provider] = None
    technical_level: Literal["low", "medium", "high"] = "medium"
    target_slides: Optional[int] = Field(default=None, ge=3, le=12)
    extra_instructions: Optional[str] = None


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    field: Optional[str] = None


class ValidationReport(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = []
    sources_checked: list[dict[str, Any]] = []


class ContentDraft(BaseModel):
    """Payload di scrittura/modifica manuale di un Content."""
    kind: ContentKind
    title: str
    hook: Optional[str] = None
    caption: str
    hashtags: str = ""
    cta: Optional[str] = None
    slides: list[Slide] = []
    reel_script: Optional[str] = None
    paper_id: Optional[int] = None
    provider: Optional[Provider] = None


class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: Optional[int] = None
    kind: str
    title: str
    hook: Optional[str] = None
    caption: str
    hashtags: str = ""
    cta: Optional[str] = None
    slides_json: Optional[Any] = None
    reel_script: Optional[str] = None
    provider: str
    model: Optional[str] = None
    validation_json: Optional[Any] = None
    status: str
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ApprovalAction(BaseModel):
    action: Literal["approve", "reject"]
    note: Optional[str] = None


class ScheduleRequest(BaseModel):
    slot_at: datetime
    channel: str = "instagram"
    notes: Optional[str] = None
