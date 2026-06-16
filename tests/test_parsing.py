"""Tests for ispipeline.parsing — GreynirEngine deep CFG parsing.

Ported from althingi/tests/test_correct_icelandic.py::TestDeepParse, with
imports rewritten to the consolidated ispipeline package. The class-level
skipif mirrors the original: the GreynirEngine-backed assertions only run when
the optional ``reynir`` dependency (``icelandic`` extra) is installed; the
graceful-degradation guard is tested unconditionally via monkeypatching.
"""

from unittest.mock import patch

import pytest

from ispipeline.parsing import (
    _HAS_GREYNIR,
    deep_parse,
    format_deep_parse_results,
)


# ── deep_parse (requires reynir / the icelandic extra) ──────────────


@pytest.mark.skipif(not _HAS_GREYNIR, reason="reynir not installed")
class TestDeepParse:
    def test_wellformed_sentence_parses(self):
        sentences = [
            ("Forsætisráðherra lagði fram frumvarp til laga.", 1),
        ]
        result = deep_parse(sentences)
        # Well-formed Icelandic sentence should parse
        assert len(result) == 0

    def test_skips_short_fragments(self):
        sentences = [("Já nei.", 1)]
        result = deep_parse(sentences)
        assert result == []

    def test_flagged_entries_have_required_fields(self):
        # Deliberately malformed
        sentences = [
            ("Frumvarp sem laga til forsætisráðherra framlagði.", 1),
        ]
        result = deep_parse(sentences)
        for entry in result:
            assert "line" in entry
            assert "text" in entry
            assert "num_tokens" in entry

    def test_empty_input(self):
        result = deep_parse([])
        assert result == []


# ── graceful degradation guard (no reynir) ─────────────────────────


def test_deep_parse_without_greynir_returns_empty():
    """Preserved guard: when reynir is unavailable, deep_parse short-circuits
    to [] rather than raising — the ``try/except ImportError`` degradation."""
    with patch("ispipeline.parsing._HAS_GREYNIR", False):
        sentences = [
            ("Forsætisráðherra lagði fram frumvarp til laga í dag.", 1),
        ]
        assert deep_parse(sentences) == []


# ── format_deep_parse_results (pure, no reynir) ────────────────────


def test_format_no_flagged_returns_zero():
    assert format_deep_parse_results([], "skjal.md") == 0


def test_format_counts_flagged():
    flagged = [
        {"line": 3, "text": "Þetta er gölluð setning sem þáttast ekki.", "num_tokens": 6},
        {"line": 7, "text": "Önnur gölluð setning hér.", "num_tokens": 4},
    ]
    assert format_deep_parse_results(flagged, "skjal.md") == 2
