"""Test sulla factory dei provider AI (senza chiamate reali)."""
import pytest

from backend.app.services.ai import AIProviderError, available_providers, get_provider


def test_no_providers_raises():
    # In conftest.py tutte le API key sono "" → nessun provider configurato
    assert available_providers() == []
    with pytest.raises(AIProviderError):
        get_provider()
