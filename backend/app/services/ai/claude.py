"""Anthropic Claude provider."""
from __future__ import annotations

import logging
from typing import Optional

from .base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: Optional[str], model: str):
        super().__init__(model)
        if not api_key:
            raise AIProviderError("ANTHROPIC_API_KEY non configurata")
        try:
            import anthropic  # noqa: WPS433
        except ImportError as e:
            raise AIProviderError(f"libreria 'anthropic' non installata: {e}")
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, *, temperature: float = 0.4,
                 max_tokens: int = 2400, json_mode: bool = False) -> AIResponse:
        # Claude non ha un json_mode nativo: chiediamo nel system prompt.
        sys_prompt = system
        if json_mode:
            sys_prompt = system + "\n\nIMPORTANTE: rispondi UNICAMENTE con JSON valido, senza markdown, senza prefissi e senza commenti."
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(f"Claude request failed: {e}") from e

        # Concatena i blocchi di testo
        text_parts: list[str] = []
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        text = "".join(text_parts).strip()
        if not text:
            raise AIProviderError("Claude ha restituito una risposta vuota")

        usage = getattr(resp, "usage", None)
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            raw={"id": getattr(resp, "id", None)},
        )
