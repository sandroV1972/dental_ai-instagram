"""Test sull'estrazione DOI/PMID dal testo (la parte di rete e' mock-ata)."""
from unittest.mock import patch

import pytest

from backend.app.services.validation.source_check import (
    DOI_RE, PMID_RE, SourceCheckResult, verify_sources_in_text,
)


def test_doi_regex_matches():
    text = "Riferimento: 10.1038/s41591-022-12345 e altro testo."
    matches = [m.group(0) for m in DOI_RE.finditer(text)]
    assert "10.1038/s41591-022-12345" in matches


def test_pmid_regex_matches():
    text = "Vedere PMID: 12345678 nel paper."
    matches = [m.group(1) for m in PMID_RE.finditer(text)]
    assert "12345678" in matches


def test_verify_sources_in_text_calls_correct_checkers():
    text = "DOI 10.1000/test e PMID: 1111111"

    with patch("backend.app.services.validation.source_check._check_doi") as mdoi, \
         patch("backend.app.services.validation.source_check._check_pmid") as mpmid:
        mdoi.return_value = SourceCheckResult("doi", "10.1000/test", True, title="ok")
        mpmid.return_value = SourceCheckResult("pmid", "1111111", True, title="ok pubmed")
        results = verify_sources_in_text(text)

    kinds = {r.kind for r in results}
    assert kinds == {"doi", "pmid"}
    mdoi.assert_called_once()
    mpmid.assert_called_once()
