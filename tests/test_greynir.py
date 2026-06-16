"""Tests for ispipeline.greynir — GreynirCorrect grammar/spelling checks.

Ported from althingi's tests/test_correct_icelandic.py (the only fork with
tests exercising this module's public functions), with imports rewritten to
``from ispipeline.greynir import ...``. Plus smoke tests for the merged
public surface: the unioned suppress list / fix codes, the in-memory
``apply_fixes_to_text``, and the graceful-ImportError guard.

Tests may assume the ``icelandic`` extra is installed; those that strictly
need BÍN are guarded by ``_HAS_ISLENSKA``.
"""

import pytest

from ispipeline.greynir import (
    AUTO_FIX_CODES,
    PHRASE_FIX_CODES,
    S004_SUPPRESS,
    _HAS_ISLENSKA,
    _is_inside_quote,
    apply_fixes,
    apply_fixes_to_text,
    check_with_library,
    format_results,
)


# ── _is_inside_quote (ported from althingi) ────────────────────────


class TestIsInsideQuote:
    def test_inside_icelandic_quote(self):
        text = "Hann sagði „orðið hér“ í dag."
        idx = text.index("orðið")
        assert _is_inside_quote(text, idx) is True

    def test_outside_quote(self):
        text = "Hann sagði „orðið“ hér í dag."
        idx = text.index("hér")
        assert _is_inside_quote(text, idx) is False

    def test_inside_angle_quote(self):
        text = "Hún benti á «orðið hér» í dag."
        idx = text.index("orðið")
        assert _is_inside_quote(text, idx) is True

    def test_no_quotes(self):
        text = "Engar tilvitnarnir hér."
        assert _is_inside_quote(text, 5) is False


# ── apply_fixes quote protection (ported from althingi) ────────────


class TestApplyFixesQuoteProtection:
    def test_skips_fix_inside_quote(self, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text(
            "Hann sagði „þetta var rettt“ í ræðunni.",
            encoding="utf-8",
        )
        results = [{
            "auto_fixable": True,
            "suggest": "rétt",
            "code": "S001",
            "text": "Orðið 'rettt' var leiðrétt í 'rétt'",
        }]
        fixes = apply_fixes(test_file, results)
        content = test_file.read_text(encoding="utf-8")
        # Fix should NOT be applied — the word is inside a direct quote
        assert "rettt" in content
        assert fixes == 0

    def test_applies_fix_outside_quote(self, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text(
            "Hún sagði „hello“ og rettt var leiðrétt.",
            encoding="utf-8",
        )
        results = [{
            "auto_fixable": True,
            "suggest": "rétt",
            "code": "S001",
            "text": "Orðið 'rettt' var leiðrétt í 'rétt'",
        }]
        fixes = apply_fixes(test_file, results)
        content = test_file.read_text(encoding="utf-8")
        # Fix should be applied — "rettt" is outside the quote
        assert "rétt" in content
        assert fixes == 1
        # The quoted text should remain untouched
        assert "hello" in content


# ── S004 safety gate (ported from althingi) ────────────────────────


@pytest.mark.skipif(not _HAS_ISLENSKA, reason="islenska not installed")
class TestS004SafetyGate:
    def test_different_lemma_fix_skipped(self, tmp_path):
        """S004 fix should be skipped when both words have different BÍN lemmas."""
        test_file = tmp_path / "test.md"
        test_file.write_text("Hún fékk plötustig í umræðunni.", encoding="utf-8")

        # Simulate a GreynirCorrect S004 annotation: plötustig → plötusig
        results = [{
            "auto_fixable": True,
            "suggest": "plötusig",
            "code": "S004",
            "text": "Orðið 'plötustig' var leiðrétt í 'plötusig'",
        }]

        from islenska import Bin

        b = Bin()
        _, stig_meanings = b.lookup("plötustig")
        _, sig_meanings = b.lookup("plötusig")

        if stig_meanings and sig_meanings:
            fixes = apply_fixes(test_file, results)
            content = test_file.read_text(encoding="utf-8")
            # The fix should NOT have been applied
            assert "plötustig" in content
            assert fixes == 0
        else:
            pytest.skip("plötustig or plötusig not in BÍN — cannot test safety gate")


# ── apply_fixes word boundary safety (ported from althingi) ────────


class TestApplyFixesBoundary:
    """apply_fixes must not corrupt compound words that contain
    the target word as a substring."""

    def test_does_not_corrupt_compound_when_compound_is_first(self, tmp_path):
        """If the fix target appears inside a compound BEFORE its standalone
        occurrence, a naive re.escape() matches the compound and corrupts it.
        Word-boundary guards prevent this.

        Uses S001 (compound-word fix) rather than S004 because S001
        bypasses the BÍN dual-lemma safety gate, isolating the
        word-boundary behaviour.
        """
        test_file = tmp_path / "sample.md"
        test_file.write_text(
            "Formannsþingið heldur áfram. Í gær lauk þingið störfum.",
            encoding="utf-8",
        )

        results = [
            {
                "line": 1,
                "code": "S001",
                "text": "Orðið 'þingið' var leiðrétt í 'þinginu'",
                "suggest": "þinginu",
                "original": "Í gær lauk þingið störfum.",
                "corrected": "Í gær lauk þinginu störfum.",
                "auto_fixable": True,
            }
        ]

        apply_fixes(test_file, results)

        content = test_file.read_text(encoding="utf-8")
        assert "Formannsþingið" in content, (
            "Compound 'Formannsþingið' must not have 'þingið' replaced"
        )
        assert "þinginu" in content, (
            "The standalone þingið should still have been replaced by the fix"
        )

    def test_does_not_match_substring_of_compound(self, tmp_path):
        """A fix on 'stig' must not replace 'stig' inside 'plötustig' when
        the compound is the only occurrence in the file.

        S001 again (bypass safety gate; isolate boundary behaviour)."""
        test_file = tmp_path / "sample.md"
        test_file.write_text(
            "Plötustig var annað í umræðunni.",
            encoding="utf-8",
        )

        results = [
            {
                "line": 1,
                "code": "S001",
                "text": "Orðið 'stig' var leiðrétt í 'stigið'",
                "suggest": "stigið",
                "original": "Plötustig var annað í umræðunni.",
                "corrected": "Plötustig var annað í umræðunni.",
                "auto_fixable": True,
            }
        ]

        apply_fixes(test_file, results)

        content = test_file.read_text(encoding="utf-8")
        assert "Plötustig" in content, (
            "Compound 'Plötustig' must not have 'stig' substring replaced"
        )
        assert "Plötustigið" not in content, "Incorrect: 'stig' replaced inside compound"


# ── Merged public surface (unioned constants + in-memory variant) ──


class TestMergedSurface:
    def test_fix_code_constants(self):
        assert AUTO_FIX_CODES == {"S004", "S001"}
        assert PHRASE_FIX_CODES == {"P_afað"}

    def test_suppress_list_unions_both_forks(self):
        # esbvaktin (EU/civic) terms
        assert "aðildarviðræður" in S004_SUPPRESS
        assert "sjávarútvegsstefna" in S004_SUPPRESS
        # althingi (parliamentary) terms
        assert "þinglífi" in S004_SUPPRESS
        assert "ræðusnild" in S004_SUPPRESS

    def test_apply_fixes_to_text_in_memory(self):
        """apply_fixes_to_text (esbvaktin) corrects a string without a file."""
        text = "Hér var rettt og ekkert annað."
        results = [{
            "auto_fixable": True,
            "suggest": "rétt",
            "code": "S001",
            "text": "Orðið 'rettt' var leiðrétt í 'rétt'",
        }]
        corrected, count = apply_fixes_to_text(text, results)
        assert count == 1
        assert "rétt" in corrected
        assert "rettt" not in corrected

    def test_apply_fixes_to_text_respects_quote_guard(self):
        """The in-memory variant honours the same in-quote guard."""
        text = "Hann sagði „þetta var rettt“ í dag."
        results = [{
            "auto_fixable": True,
            "suggest": "rétt",
            "code": "S001",
            "text": "Orðið 'rettt' var leiðrétt í 'rétt'",
        }]
        corrected, count = apply_fixes_to_text(text, results)
        assert count == 0
        assert "rettt" in corrected

    def test_s004_suppress_blocks_known_compound(self):
        """A suppressed S004 word is never 'corrected' (preserved guard)."""
        text = "Ný aðildarviðræður hófust."
        results = [{
            "auto_fixable": True,
            "suggest": "aðildarviðræðum",
            "code": "S004",
            "text": "Orðið 'aðildarviðræður' var leiðrétt í 'aðildarviðræðum'",
        }]
        corrected, count = apply_fixes_to_text(text, results)
        assert count == 0
        assert "aðildarviðræður" in corrected


# ── Graceful ImportError degradation (esbvaktin guard) ─────────────


class TestGracefulDegradation:
    def test_check_with_library_returns_empty_without_reynir(self, monkeypatch):
        """When reynir_correct is unavailable, check_with_library returns []
        instead of sys.exit(1) — the rest of the pipeline keeps running.

        Forces the ImportError branch by hiding the module and resetting the
        cached availability flag.
        """
        import builtins

        import ispipeline.greynir as greynir_mod

        monkeypatch.setattr(greynir_mod, "_reynir_available", None, raising=False)

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "reynir_correct":
                raise ImportError("simulated: reynir_correct not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        out = check_with_library([("Þetta er prófun.", 1)])
        assert out == []


# ── format_results smoke (preserved in both forks) ─────────────────


class TestFormatResults:
    def test_empty_results(self, capsys):
        errors, warnings, auto_fixable = format_results([], "sample.md")
        assert (errors, warnings, auto_fixable) == (0, 0, 0)

    def test_counts_categories(self):
        results = [
            {"line": 1, "code": "S004", "text": "x", "suggest": "y",
             "detail": "", "auto_fixable": True},
            {"line": 2, "code": "P_afað", "text": "x", "suggest": "",
             "detail": "", "auto_fixable": False},
            {"line": 3, "code": "Z999", "text": "x", "suggest": "",
             "detail": "", "auto_fixable": False},
        ]
        errors, warnings, auto_fixable = format_results(results, "sample.md")
        assert auto_fixable == 1
        assert errors == 1  # P_ prefix
        assert warnings == 1
