"""Tests for ispipeline.naturalness — Icegrams trigram scoring + heuristic checks.

Ported from the althingi fork's test_correct_icelandic.py (the only fork test
that exercised the naturalness module's public functions). Imports rewritten to
the consolidated ispipeline package. Tests may assume the `icelandic` extra is
installed; the trigram tests skip gracefully when icegrams is absent.
"""

import pytest

from ispipeline.naturalness import (
    _HAS_ICEGRAMS,
    check_hedging,
    check_missing_icelandic_chars,
    check_monotonous_openings,
    check_overformal_register,
    format_heuristic_results,
    run_heuristic_checks,
    score_naturalness,
)


# ── score_naturalness (requires icegrams) ───────────────────────


@pytest.mark.skipif(not _HAS_ICEGRAMS, reason="icegrams not installed")
class TestNaturalness:
    def test_returns_list(self):
        sentences = [
            ("Forsætisráðherra lagði fram frumvarp til laga.", 1),
            ("Þetta er einfalt Íslenskt mál.", 2),
        ]
        result = score_naturalness(sentences)
        assert isinstance(result, list)

    def test_skips_short_sentences(self):
        sentences = [("Já.", 1), ("Nei.", 2)]
        result = score_naturalness(sentences)
        assert result == []

    def test_empty_input(self):
        result = score_naturalness([])
        assert result == []

    def test_flagged_entries_have_required_fields(self):
        # Use a mix of natural and deliberately odd sentences
        sentences = [
            ("Forsætisráðherra lagði fram frumvarp um efnahagsmál.", 1),
            ("Nefndin fjallaði um tillöguna á fundi sínum í gær.", 2),
            ("Þingmaðurinn tók til máls í umræðunni.", 3),
            ("Atkvæðagreiðslan fór fram klukkan tíu.", 4),
            ("Stjórnarandstaðan lagðist gegn frumvarpinu.", 5),
            # Deliberately awkward sentence
            ("Hugmyndafræði smíðaði hlið sem raunsæi opnaði samhliða.", 6),
        ]
        result = score_naturalness(sentences, threshold_sigma=1.0)
        for entry in result:
            assert "line" in entry
            assert "text" in entry
            assert "score" in entry
            assert "mean" in entry
            assert "sigma_below" in entry


def test_score_naturalness_guard_without_icegrams(monkeypatch):
    """Preserved guard: when icegrams is unavailable the scorer returns [] and
    never imports Ngrams. Force the no-icegrams branch regardless of install."""
    import ispipeline.naturalness as nat

    monkeypatch.setattr(nat, "_HAS_ICEGRAMS", False)
    sentences = [("Forsætisráðherra lagði fram frumvarp um efnahagsmál sem varðar marga.", 1)]
    assert nat.score_naturalness(sentences) == []


# ── Heuristic checks (no dependencies) ──────────────────────────


class TestHeuristicChecks:
    """Pattern-based anti-exemplar detection for translationese that
    GreynirCorrect/BÍN/Icegrams structurally cannot catch."""

    def test_monotonous_openings_flags_three_same_first_word(self):
        sents = [
            ("Samkvæmt skýrslunni er staðan slæm.", 1),
            ("Samkvæmt ráðherra er hún góð.", 2),
            ("Samkvæmt stjórnarandstöðu er hún óljós.", 3),
        ]
        flagged = check_monotonous_openings(sents)
        assert len(flagged) == 1
        assert flagged[0]["pattern"] == "samkvæmt"
        assert flagged[0]["line"] == 1

    def test_monotonous_openings_ignores_varied(self):
        sents = [
            ("Ráðherra talaði.", 1),
            ("Þingið greiddi atkvæði.", 2),
            ("Nefndin fundaði.", 3),
        ]
        assert check_monotonous_openings(sents) == []

    def test_hedging_flags_translationese_phrase(self):
        sents = [("Þetta virðist benda til þess að frumvarpið falli.", 4)]
        flagged = check_hedging(sents)
        assert len(flagged) == 1
        assert flagged[0]["line"] == 4

    def test_missing_icelandic_chars_flags_long_ascii(self):
        ascii_text = (
            "frumvarp um skatt a fyrirtaeki sem starfa i landinu og greida "
            "gjald til rikis vegna reksturs og tekna sinna a arinu"
        )
        flagged = check_missing_icelandic_chars([(ascii_text, 5)])
        assert len(flagged) == 1
        assert flagged[0]["line"] == 5

    def test_missing_icelandic_chars_ok_with_special_chars(self):
        sents = [
            (
                "Þetta er löng íslensk málsgrein með mörgum orðum og íslenskum "
                "sérstöfum sem sýna að hún er í fullkomnu lagi og eðlileg.",
                1,
            )
        ]
        assert check_missing_icelandic_chars(sents) == []

    def test_overformal_register_flags_hinsvegar(self):
        flagged = check_overformal_register([("Hinsvegar var frumvarpið fellt.", 1)])
        assert len(flagged) == 1

    def test_run_heuristic_checks_returns_all_four_keys(self):
        result = run_heuristic_checks([("Ráðherra talaði skýrt.", 1)])
        assert set(result.keys()) == {
            "monotonous_openings",
            "hedging",
            "missing_icelandic_chars",
            "overformal_register",
        }


def test_format_heuristic_results_clean_returns_zero(capsys):
    """format_heuristic_results returns the total flagged count (0 when clean)."""
    results = run_heuristic_checks([("Ráðherra talaði skýrt og af einurð.", 1)])
    total = format_heuristic_results(results, "smoke.md")
    assert total == 0
