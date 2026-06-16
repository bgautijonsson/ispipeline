"""Tests for ispipeline.confusables — LLM confusable-word pattern scanner.

Ported from the althingi forks:
  - althingi/tests/test_correct_icelandic.py  (TestConfusables, TestWeakSuperlativeUmlaut)
  - althingi/tests/test_digest_audit_prevention.py  (TestDoubleWordDetection)

Imports rewritten to ``from ispipeline.confusables import ...``. Tests that
exercised quote-stripping (``strip_direct_quotes_keep_lines``) are NOT ported
here — that helper lives in the preprocessing module, not confusables.

Two extra guard tests assert ESBvaktin-specific behaviour preserved by the
merge: the disabled-pattern filter, and ASCII-transliteration detection.
"""

from ispipeline.confusables import (
    CONFUSABLE_PATTERNS,
    check_confusables,
    format_confusable_results,
)


# ── check_confusables (ported from test_correct_icelandic.py) ──────────


class TestConfusables:
    def test_detects_bidur_upp_a(self):
        text = "Ráðherrann bíður upp á nýja leið."
        result = check_confusables(text)
        assert len(result) >= 1
        assert any("bíð" in w["description"] for w in result)

    def test_detects_a_vikunni(self):
        text = "Þetta gerðist á vikunni sem leið."
        result = check_confusables(text)
        assert len(result) >= 1
        assert any("í vikunni" in (w.get("suggestion") or "") for w in result)

    def test_detects_a_thessari_viku(self):
        text = "Á þessari viku voru margar ræður."
        result = check_confusables(text)
        assert len(result) >= 1

    def test_detects_plotusig(self):
        text = "Flokkurinn fékk plötusig í umræðunni."
        result = check_confusables(text)
        assert len(result) >= 1
        assert any("plötustig" in (w.get("suggestion") or "") for w in result)

    def test_clean_text_no_warnings(self):
        text = "Forsætisráðherra lagði fram frumvarp til laga."
        result = check_confusables(text)
        assert result == []

    def test_tracks_line_numbers(self):
        text = "Lína eitt.\nHún bíður upp á breytingu.\nLína þrjú."
        result = check_confusables(text)
        assert len(result) >= 1
        assert result[0]["line"] == 2

    def test_returns_required_fields(self):
        text = "Hún bíður upp á eitthvað."
        result = check_confusables(text)
        for entry in result:
            assert "line" in entry
            assert "match" in entry
            assert "description" in entry
            assert "suggestion" in entry
            assert "context" in entry

    def test_empty_input(self):
        assert check_confusables("") == []

    def test_confusable_patterns_not_empty(self):
        """Ensure the pattern list has entries."""
        assert len(CONFUSABLE_PATTERNS) >= 5


# ── Weak-superlative u-umlaut (ported, althingi) ───────────────────────


class TestWeakSuperlativeUmlaut:
    """Weak superlative in acc/dat/gen with u-ending triggers u-umlaut:
    'skarpastu' → 'skörpustu'. GreynirCorrect previously overcorrected
    this in the wrong direction; promoted to canonical confusables
    (audit finding P1.D2)."""

    def test_flags_skarpastu(self):
        text = "Hún hafði skarpastu spurningarnar vikunnar."
        results = check_confusables(text)
        matches = [r["match"].lower() for r in results]
        assert any("skarpastu" in m for m in matches), (
            f"Expected 'skarpastu' to be flagged; got matches: {matches}"
        )

    def test_does_not_flag_skorpustu(self):
        """The correct form 'skörpustu' must not be flagged."""
        text = "Hún hafði skörpustu spurningarnar vikunnar."
        results = check_confusables(text)
        matches = [r["match"].lower() for r in results]
        assert not any("skörpustu" in m for m in matches), (
            f"'skörpustu' is correct and must not be flagged; got: {matches}"
        )

    def test_suggests_correct_form(self):
        text = "skarpastu málsvörnin var frá oddvitanum."
        results = check_confusables(text)
        skarp_flags = [r for r in results if "skarpastu" in r["match"].lower()]
        assert skarp_flags
        assert any(
            "skörpustu" in (r.get("suggestion") or "").lower() for r in skarp_flags
        ), f"Expected 'skörpustu' in suggestion; got: {skarp_flags}"


# ── Double-word detection (ported from test_digest_audit_prevention.py) ─


class TestDoubleWordDetection:
    """C1: Confusables pipeline catches repeated adjacent words."""

    def test_catches_yfir_yfir(self):
        text = "Hún fór þar vandlega yfir yfir sextíu gjaldaliðahækkanir."
        warnings = check_confusables(text)
        doubled = [w for w in warnings if "Repeated word" in w.get("description", "")]
        assert len(doubled) >= 1

    def test_catches_sagdi_sagdi(self):
        text = "Hún sagði sagði að þetta væri í lagi."
        warnings = check_confusables(text)
        doubled = [w for w in warnings if "Repeated word" in w.get("description", "")]
        assert len(doubled) >= 1

    def test_no_false_positive_on_separated_words(self):
        text = "Þetta er gott og vel gott."
        warnings = check_confusables(text)
        doubled = [w for w in warnings if "Repeated word" in w.get("description", "")]
        assert len(doubled) == 0

    def test_no_false_positive_on_short_words(self):
        text = "Hún fór og og kom aftur."
        warnings = check_confusables(text)
        doubled = [w for w in warnings if "Repeated word" in w.get("description", "")]
        assert len(doubled) == 0  # "og" is only 2 chars, below threshold


# ── Preserved-guard tests (ESBvaktin behaviour kept by the union) ──────


class TestEsbvaktinGuardsPreserved:
    def test_ascii_transliteration_detection(self):
        """ESBvaktin's signature ASCII-transliteration guard must fire on
        ASCII-ified Icelandic ('landbun...' for 'landbún...')."""
        text = "Stefnan um landbunad er til umfjollunar."
        warnings = check_confusables(text)
        assert any("ASCII transliteration" in w["description"] for w in warnings), (
            f"Expected an ASCII-transliteration warning; got: {warnings}"
        )

    def test_disabled_pattern_filter_fires(self):
        """The merge preserves ESBvaktin's disabled-pattern convention: entries
        whose description is None are filtered out of CONFUSABLE_PATTERNS. The
        deliberately-disabled '\\b(?:ad|af|vid|til)\\b' pattern (too many false
        positives) must NOT survive into the active list."""
        disabled_regex = r"\b(?:ad|af|vid|til)\b(?=\s+[a-z])"
        assert all(p != disabled_regex for p, _d, _s in CONFUSABLE_PATTERNS), (
            "Disabled pattern leaked into active CONFUSABLE_PATTERNS"
        )
        # And every surviving entry must have a non-None description.
        assert all(d is not None for _p, d, _s in CONFUSABLE_PATTERNS)


# ── format_confusable_results smoke ───────────────────────────────────


def test_format_confusable_results_counts(capsys):
    warnings = check_confusables("Hún bíður upp á eitthvað.")
    n = format_confusable_results(warnings, "test.md")
    assert n == len(warnings) >= 1


def test_format_confusable_results_empty(capsys):
    n = format_confusable_results([], "clean.md")
    assert n == 0
    out = capsys.readouterr().out
    assert "No confusable-word patterns found" in out
