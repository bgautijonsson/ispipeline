"""Tests for ispipeline.inflections — BÍN inflection validation layer.

Ported from althingi's test_correct_icelandic.py (TestExtractWords,
TestInflections), with imports rewritten to ``ispipeline.inflections``. Tests
that touch BÍN are skipped when the optional ``icelandic`` extra is absent.
Additional tests assert the merged (unioned) skiplist and the graceful
``_HAS_ISLENSKA`` degradation guard.
"""

from unittest.mock import patch

import pytest

from ispipeline.inflections import (
    _INFLECTION_SKIPLIST,
    _HAS_ISLENSKA,
    _extract_words,
    check_inflections,
    format_inflection_results,
)


# ── _extract_words ─────────────────────────────────────────────


class TestExtractWords:
    def test_basic(self):
        words = _extract_words("Þetta er prófun.")
        assert "Þetta" in words
        assert "er" in words
        assert "prófun" in words

    def test_skips_numbers_and_punctuation(self):
        words = _extract_words("Árið 2026, 15 þingmenn.")
        assert "2026" not in words
        assert "15" not in words
        assert "Árið" in words
        assert "þingmenn" in words

    def test_skips_single_chars(self):
        words = _extract_words("A b C test")
        assert "A" not in words
        assert "b" not in words
        assert "test" in words


# ── check_inflections ──────────────────────────────────────────


@pytest.mark.skipif(not _HAS_ISLENSKA, reason="islenska not installed")
class TestInflections:
    def test_valid_words_not_flagged(self):
        sentences = [
            ("Forsætisráðherra lagði fram frumvarp til laga.", 1),
        ]
        result = check_inflections(sentences)
        # Common well-formed words should not be flagged
        flagged_words = [f["word"] for f in result]
        assert "forsætisráðherra" not in [w.lower() for w in flagged_words]

    def test_invented_word_flagged(self):
        sentences = [
            ("Þetta er glæsiblyrkkja í þinginu.", 1),
        ]
        result = check_inflections(sentences)
        flagged_words = [f["word"].lower() for f in result]
        assert "glæsiblyrkkja" in flagged_words

    def test_skips_capitalised_mid_sentence(self):
        sentences = [
            ("Kristrún Frostadóttir tók til máls.", 1),
        ]
        result = check_inflections(sentences)
        flagged_words = [f["word"] for f in result]
        # "Frostadóttir" is capitalised mid-sentence, should be skipped
        assert "Frostadóttir" not in flagged_words

    def test_skips_skiplist_words(self):
        sentences = [
            ("Hún sagði já og nei í ræðunni.", 1),
        ]
        result = check_inflections(sentences)
        flagged_words = [f["word"].lower() for f in result]
        assert "já" not in flagged_words
        assert "nei" not in flagged_words

    def test_empty_input(self):
        result = check_inflections([])
        assert result == []

    def test_flagged_entries_have_required_fields(self):
        sentences = [("Hér er glæsiblyrkkja.", 1)]
        result = check_inflections(sentences)
        for entry in result:
            assert "line" in entry
            assert "word" in entry
            assert "context" in entry


# ── merged skiplist (UNION of both forks) ──────────────────────


class TestMergedSkiplist:
    def test_eu_entries_preserved(self):
        # esbvaktin domain entries must survive the merge
        for w in ("acquis", "communautaire", "screening", "efta", "ESB", "EES"):
            assert w in _INFLECTION_SKIPLIST

    def test_parliamentary_entries_preserved(self):
        # althingi domain entries must survive the merge
        for w in ("hv", "þm", "sveipulisti", "þegjendurnir", "endurtakararnir"):
            assert w in _INFLECTION_SKIPLIST

    def test_shared_entries_present(self):
        for w in ("skv", "sbr", "nr", "gr", "mgr", "já", "nei", "spin", "status"):
            assert w in _INFLECTION_SKIPLIST


# ── degradation guard ──────────────────────────────────────────


class TestDegradationGuard:
    def test_returns_empty_when_islenska_absent(self):
        # The _HAS_ISLENSKA guard must short-circuit to [] when BÍN is unavailable,
        # never raising even on non-trivial input.
        with patch("ispipeline.inflections._HAS_ISLENSKA", False):
            result = check_inflections([("Þetta er glæsiblyrkkja.", 1)])
            assert result == []


# ── format_inflection_results ──────────────────────────────────


class TestFormatResults:
    def test_no_flags_returns_zero(self):
        assert format_inflection_results([], "test.md") == 0

    def test_counts_flagged_words(self):
        flagged = [
            {"line": 1, "word": "glæsiblyrkkja", "context": "Hér er glæsiblyrkkja."},
            {"line": 2, "word": "endurtakararnir", "context": "Og endurtakararnir."},
        ]
        assert format_inflection_results(flagged, "test.md") == 2
