"""Google Gemini provider."""
from __future__ import annotations

import logging
from typing import Optional

from .base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str], model: str):
        super().__init__(model)
        if not api_key:
            raise AIProviderError("GOOGLE_API_KEY non configurata")
        try:
            import google.generativeai as genai  # noqa: WPS433
        except ImportError as e:
            raise AIProviderError(f"libreria 'google-generativeai' non installata: {e}")
        genai.configure(api_key=api_key)
        self._genai = genai

    def complete(self, system: str, user: str, *, temperature: float = 0.4,
                 max_tokens: int = 2400, json_mode: bool = False) -> AIResponse:
        gen_cfg = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            gen_cfg["response_mime_type"] = "application/json"
        try:
            model_obj = self._genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system,
                generation_config=gen_cfg,
            )
            resp = model_obj.generate_content(user)
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(f"Gemini request failed: {e}") from e

        text = (getattr(resp, "text", None) or "").strip()
        if not text:
            raise AIProviderError("Gemini ha restituito una risposta vuota")
        usage = getattr(resp, "usage_metadata", None)
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            raw={},
        )
