"""Test del repair JSON per risposte AI troncate (max_tokens hit)."""
import json

from backend.app.services.generation.generator import _extract_json, _try_repair_truncated_json


def test_extract_clean_json():
    s = '{"title": "ok", "caption": "x"}'
    assert _extract_json(s) == {"title": "ok", "caption": "x"}


def test_extract_with_markdown_fence():
    s = '```json\n{"title": "ok"}\n```'
    assert _extract_json(s) == {"title": "ok"}


def test_repair_string_truncated():
    # caption rimasta aperta a meta'
    truncated = '{"title": "La nascita dell\'AI", "hook": "Sai quando?", "caption": "Oggi parliam'
    out = _extract_json(truncated)
    # title e hook devono essere preservati; caption puo' essere chiusa o assente
    assert out["title"] == "La nascita dell'AI"
    assert out["hook"] == "Sai quando?"


def test_repair_object_truncated_after_complete_field():
    # tagliato dopo una virgola valida
    truncated = '{"title": "AI", "hook": "x",'
    out = _extract_json(truncated)
    assert out["title"] == "AI"
    assert out["hook"] == "x"


def test_repair_carousel_with_slides_truncated():
    truncated = (
        '{"title": "AI in radiologia", "hook": "Come funziona",'
        ' "slides": [{"index": 1, "title": "Intro", "body": "Testo intro"},'
        ' {"index": 2, "title": "Dettaglio", "body": "Inizio'
    )
    out = _extract_json(truncated)
    assert out["title"] == "AI in radiologia"
    assert isinstance(out["slides"], list)
    assert out["slides"][0]["title"] == "Intro"


def test_extract_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        _extract_json("")


def test_repair_only_braces():
    # solo apertura
    out = _try_repair_truncated_json("{")
    assert out.endswith("}")
    assert json.loads(out) == {}
