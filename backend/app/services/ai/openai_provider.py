"""OpenAI provider (GPT-4o e simili)."""
from __future__ import annotations

import logging
from typing import Optional

from .base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str], model: str):
        super().__init__(model)
        if not api_key:
            raise AIProviderError("OPENAI_API_KEY non configurata")
        try:
            from openai import OpenAI  # noqa: WPS433
        except ImportError as e:
            raise AIProviderError(f"libreria 'openai' non installata: {e}")
        self._client = OpenAI(api_key=api_key)

    def complete(self, system: str, user: str, *, temperature: float = 0.4,
                 max_tokens: int = 2400, json_mode: bool = False) -> AIResponse:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(f"OpenAI request failed: {e}") from e

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            raise AIProviderError("OpenAI ha restituito una risposta vuota")
        usage = getattr(resp, "usage", None)
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            raw={"id": getattr(resp, "id", None)},
        )
