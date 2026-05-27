"""DeepSeek provider tramite endpoint OpenAI-compatibile.

Docs: https://api-docs.deepseek.com/  (gli endpoint sono OpenAI-compatibili,
quindi riusiamo l'SDK openai puntando a https://api.deepseek.com).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekProvider(AIProvider):
    name = "deepseek"

    def __init__(self, api_key: Optional[str], model: str):
        super().__init__(model)
        if not api_key:
            raise AIProviderError("DEEPSEEK_API_KEY non configurata")
        self._api_key = api_key

    def complete(self, system: str, user: str, *, temperature: float = 0.4,
                 max_tokens: int = 2400, json_mode: bool = False) -> AIResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                json=payload, headers=headers, timeout=60.0,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise AIProviderError(f"DeepSeek request failed: {e}") from e

        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise AIProviderError(f"DeepSeek risposta malformata: {data}") from e
        usage = data.get("usage") or {}
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw={"id": data.get("id")},
        )
