"""Factory dei provider AI con fallback ordinato sui provider configurati."""
from __future__ import annotations

import logging
from typing import Optional

from ...core.config import settings
from .base import AIProvider, AIProviderError

logger = logging.getLogger(__name__)


def available_providers() -> list[str]:
    return list(settings.configured_providers)


def get_provider(name: Optional[str] = None) -> AIProvider:
    """Restituisce un provider istanziato.

    - Se `name` e' passato, lo usa (errore se non configurato).
    - Altrimenti usa `DEFAULT_AI_PROVIDER`; se non configurato, sceglie il primo
      provider che ha la propria API key.
    """
    target = (name or settings.DEFAULT_AI_PROVIDER).lower()
    configured = settings.configured_providers
    if not configured:
        raise AIProviderError(
            "Nessun provider AI configurato. Imposta almeno una API key in .env "
            "(ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY / DEEPSEEK_API_KEY)."
        )
    if name is None and target not in configured:
        # default non configurato: fallback al primo disponibile
        fallback = configured[0]
        logger.warning("Default provider %s non configurato, uso %s", target, fallback)
        target = fallback

    if target == "claude":
        from .claude import ClaudeProvider
        return ClaudeProvider(settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL)
    if target == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.OPENAI_MODEL)
    if target == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(settings.GOOGLE_API_KEY, settings.GEMINI_MODEL)
    if target == "deepseek":
        from .deepseek import DeepSeekProvider
        return DeepSeekProvider(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_MODEL)

    raise AIProviderError(f"Provider sconosciuto: {target}")
