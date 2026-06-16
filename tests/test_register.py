"""Tests for ispipeline.register — borrowing blocklist + compound-length.

Ported verbatim from althingi's tests/test_register.py, with imports
rewritten to ``ispipeline.register`` (the original ``sys.path`` shim and
``from corrections.register import ...`` are dropped). Covers both
check_register (English-loanword blocklist) and check_compound_length
(over-long compound heuristic).
"""

from ispipeline.register import (
    REGISTER_BLOCKLIST,
    check_register,
    check_compound_length,
)


class TestRegisterBlocklist:
    def test_catches_all_blocklisted_words(self):
        """Every word in REGISTER_BLOCKLIST must be flagged when present."""
        for word, _suggestion in REGISTER_BLOCKLIST:
            sentence = f"Þetta er bara {word} í raun."
            results = check_register(sentence)
            flagged = {r["word"].lower() for r in results}
            assert word.lower() in flagged, (
                f"{word!r} not flagged; got {flagged}"
            )

    def test_case_insensitive_match(self):
        results = check_register("Tilvikið var OKEI að lokum.")
        assert len(results) == 1
        assert results[0]["word"].lower() == "okei"

    def test_word_boundary_required(self):
        """'okei' must not match as a substring of a longer word."""
        results = check_register("Hann kom úr pokeinum — óvenjulegt.")
        words = {r["word"].lower() for r in results}
        assert "okei" not in words, (
            "'okei' should not match inside 'pokeinum'"
        )

    def test_context_window_extraction(self):
        """Context is a bounded window around the match, with ellipses."""
        long_line = "A" * 50 + " póint " + "B" * 50
        results = check_register(long_line)
        assert len(results) == 1
        ctx = results[0]["context"]
        assert "póint" in ctx
        # Context should be bounded — not the full ~100-char line
        assert len(ctx) <= 80

    def test_line_number_tracking(self):
        text = "First line here.\nAnd this djók here.\nThird line."
        results = check_register(text)
        assert len(results) == 1
        assert results[0]["line"] == 2

    def test_multiple_borrowings_in_text(self):
        text = "Hann var stressað — algjört djók að lokum. Basic dæmi."
        results = check_register(text)
        flagged = {r["word"].lower() for r in results}
        assert "stressað" in flagged
        assert "djók" in flagged
        assert "basic" in flagged
        assert len(results) == 3

    def test_suggestion_included(self):
        results = check_register("Aðalatriðið er að ná fokus.")
        assert len(results) == 1
        assert "áhersla" in results[0]["suggestion"].lower() or (
            "brennipunkt" in results[0]["suggestion"].lower()
        )

    def test_clean_text_flags_nothing(self):
        text = (
            "Nefndin tók fyrir frumvarpið og afgreiddi það til 2. umræðu. "
            "Tillagan var samþykkt með 32 atkvæðum gegn 28."
        )
        assert check_register(text) == []


class TestCompoundLength:
    def test_flags_word_over_default_threshold(self):
        word = "samfélagsmálaráðuneytisskrifstofustjórinn"
        assert len(word) > 25
        text = f"Orðið {word} kom fram."
        results = check_compound_length(text)
        assert len(results) == 1
        assert results[0]["length"] == len(word)

    def test_word_at_threshold_not_flagged(self):
        """A word of exactly 25 chars is not flagged (> is strict, not >=)."""
        word = "a" * 25
        assert len(word) == 25
        text = f"Þetta er {word} staðfest."
        results = check_compound_length(text)
        flagged = [r["word"] for r in results]
        assert word not in flagged

    def test_flags_multiple_long_words(self):
        text = (
            "Umhverfisvernarstofnunarstjórinn og "
            "mannréttindadómstólshandlangarinn voru til staðar."
        )
        results = check_compound_length(text)
        assert len(results) >= 2

    def test_respects_custom_max(self):
        """With max_chars=5, 'Frumvarpið' (10) and 'samþykkt' (8) flag."""
        results = check_compound_length("Frumvarpið var samþykkt.", max_chars=5)
        long_words = {r["word"] for r in results}
        assert "Frumvarpið" in long_words
        assert "samþykkt" in long_words

    def test_line_number_tracking(self):
        text = "Short first line.\nVeldissprengjuefnahagskerfiðanna var rætt í gær."
        results = check_compound_length(text)
        assert len(results) == 1
        assert results[0]["line"] == 2

    def test_strips_trailing_punctuation(self):
        """Punctuation at the edge is stripped before length measurement."""
        word = "ráðherrafjölskyldumedlimur"
        assert len(word) > 25
        text = f"Einhver {word}, svo sem forstöðumaður..."
        results = check_compound_length(text)
        flagged = [r["word"] for r in results]
        assert word in flagged, (
            f"Expected {word!r} (sans comma) in {flagged}"
        )

    def test_short_normal_words_not_flagged(self):
        """Short normal sentences produce no flags at the default threshold."""
        text = "Þingmaðurinn er 35 ára og starfar á Alþingi."
        results = check_compound_length(text)
        assert results == []

    def test_non_alphabetic_tokens_skipped(self):
        """Long digit strings or mixed tokens should not be flagged — the
        check requires word.isalpha()."""
        text = "Fjárlagatalan er 123456789012345678901234567890."
        results = check_compound_length(text)
        # The digit string is >25 chars but not alphabetic
        long_numbers = [r["word"] for r in results if not r["word"].isalpha()]
        assert long_numbers == []
