"""Astrazione comune ai provider AI (Claude/OpenAI/Gemini/DeepSeek).

Tutti i provider devono restituire testo plain o JSON parsabile. Il caller
decide come deserializzare. Manteniamo l'interfaccia *sincrona* perche'
FastAPI puo' offloadare automaticamente le route sincrone in threadpool, e
le SDK ufficiali (anthropic, openai, google-generativeai) offrono entrambe
le forme; usare la sincrona riduce complessita' del codice cliente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class AIProviderError(RuntimeError):
    """Errore generico di un provider AI (config mancante, rate limit, response malformata)."""


@dataclass
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    raw: dict = field(default_factory=dict)


class AIProvider:
    """Interfaccia base. Le sottoclassi implementano `complete`."""

    name: str = "base"

    def __init__(self, model: str):
        self.model = model

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 2400,
        json_mode: bool = False,
    ) -> AIResponse:
        raise NotImplementedError
