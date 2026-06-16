"""Tests for ispipeline.preprocessing — markdown stripping, tweets JSON
conversion, and Icelandic typography normalization.

Ported from althingi's test_correct_icelandic.py (TestTypographyNormalization,
TestStripMarkdown, TestStripDirectQuotes, TestStripDirectQuotesKeepLines), with
imports rewritten to ``ispipeline.preprocessing``. The confusables-dependent
cases from the original TestStripDirectQuotesKeepLines section live in the
confusables module's test file, not here.

Additional tests cover ``tweets_json_to_text`` (a public export not directly
exercised by the althingi suite) and assert the ``_HAS_TOKENIZER`` graceful
``try/except ImportError`` degradation guard (fallback to one-entry-per-line).
"""

import json
from unittest.mock import patch

from ispipeline.preprocessing import (
    _strip_direct_quotes,
    count_typography_issues,
    fix_typography_in_file,
    fix_typography_in_tweets_file,
    normalize_typography,
    strip_direct_quotes_keep_lines,
    strip_markdown_formatting,
    tweets_json_to_text,
)


# ── normalize_typography ────────────────────────────────────────


class TestTypographyNormalization:
    def test_fixes_straight_closing_quote(self):
        assert normalize_typography('Hvað eru „rauðu strikin"?') == 'Hvað eru „rauðu strikin”?'

    def test_idempotent(self):
        already_correct = 'Hvað eru „rauðu strikin”?'
        assert normalize_typography(already_correct) == already_correct
        assert count_typography_issues(already_correct) == 0

    def test_fixes_multiple_pairs(self):
        text = 'Eitt: „foo" og annað: „bar"'
        assert normalize_typography(text) == 'Eitt: „foo” og annað: „bar”'
        assert count_typography_issues(text) == 2

    def test_ignores_straight_quotes_without_opener(self):
        text = 'Straight everywhere: "foo" "bar"'
        assert normalize_typography(text) == text
        assert count_typography_issues(text) == 0

    def test_does_not_match_across_paragraphs(self):
        text = '„foo bar baz\n\nNext paragraph: "x"'
        # No straight closer paired with the opener; the orphan opener stays as-is.
        # The standalone "x" has no matching „, so it stays straight.
        assert count_typography_issues(text) == 0

    def test_fix_in_tweets_file_writes_back(self, tmp_path):
        f = tmp_path / "tweets.json"
        f.write_text(
            json.dumps(
                {
                    "thread": [{"text": 'Hvað eru „rauðu strikin"?'}],
                    "quotes": [{"text": 'Other „issue" too'}],
                    "quote_threads": [{"tweets": [{"text": 'Nested „foo"'}]}],
                },
                ensure_ascii=False,
            )
        )
        applied = fix_typography_in_tweets_file(f)
        assert applied == 3
        result = json.loads(f.read_text())
        assert result["thread"][0]["text"] == 'Hvað eru „rauðu strikin”?'
        assert result["quotes"][0]["text"] == 'Other „issue” too'
        assert result["quote_threads"][0]["tweets"][0]["text"] == 'Nested „foo”'

    def test_fix_in_md_file_no_change_returns_zero(self, tmp_path):
        f = tmp_path / "clean.md"
        f.write_text("All clean text here.\n")
        assert fix_typography_in_file(f) == 0


# ── strip_markdown_formatting ──────────────────────────────────


class TestStripMarkdown:
    def test_skips_headings(self):
        text = "## Heading\n\nSome actual content here."
        sentences = strip_markdown_formatting(text)
        assert len(sentences) == 1
        # tokenizer may normalise whitespace around punctuation
        assert "Some actual content here" in sentences[0][0]

    def test_skips_code_blocks(self):
        text = "Before code.\n\n```python\ncode_here()\n```\n\nAfter code."
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert "code_here()" not in texts
        assert any("Before code" in t for t in texts)
        assert any("After code" in t for t in texts)

    def test_skips_frontmatter(self):
        text = "---\ntitle: Test\n---\n\nActual content."
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert not any("title" in t for t in texts)
        assert any("Actual content" in t for t in texts)

    def test_strips_bold_italic(self):
        text = "This is **bold** and *italic* text."
        sentences = strip_markdown_formatting(text)
        # tokenizer may normalise whitespace around punctuation
        assert "This is bold and italic text" in sentences[0][0]

    def test_strips_links(self):
        text = "See [this link](https://example.com) for details."
        sentences = strip_markdown_formatting(text)
        assert "See this link for details" in sentences[0][0]

    def test_skips_table_separators(self):
        text = "| Header |\n|--------|\n| Data |"
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert not any("---" in t for t in texts)

    def test_tracks_line_numbers(self):
        text = "\n\nLine three here.\n\nLine five here."
        sentences = strip_markdown_formatting(text)
        assert sentences[0][1] == 3
        assert sentences[1][1] == 5

    def test_strips_list_markers(self):
        text = "- Item one\n- Item two\n1. Numbered item"
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert "Item one" in texts
        assert "Item two" in texts
        assert "Numbered item" in texts

    def test_empty_input(self):
        assert strip_markdown_formatting("") == []
        assert strip_markdown_formatting("## Only heading") == []

    def test_icelandic_content(self):
        text = "Þetta er **íslenskt** efni með *sérstökum* stöfum."
        sentences = strip_markdown_formatting(text)
        assert "Þetta er íslenskt efni með sérstökum stöfum" in sentences[0][0]

    def test_strips_icelandic_quotes(self):
        text = 'Hann sagði „Við þurfum aðgerðir“ og hélt áfram.'
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        # The quoted text should be removed
        assert not any("Við þurfum aðgerðir" in t for t in texts)
        # The surrounding narrative should remain
        assert any("Hann sagði" in t for t in texts)

    def test_strips_angle_quotes(self):
        text = "Hún benti á «mikilvægi breytinga» í ræðunni."
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert not any("mikilvægi breytinga" in t for t in texts)
        assert any("Hún benti á" in t for t in texts)

    def test_strips_multiple_quotes(self):
        text = '„Fyrsta“ og „Önnur“ tilvitnun.'
        sentences = strip_markdown_formatting(text)
        texts = [s[0] for s in sentences]
        assert not any("Fyrsta" in t for t in texts)
        assert not any("Önnur" in t for t in texts)

    def test_protect_quotes_false_keeps_quotes(self):
        text = 'Hann sagði „Við þurfum aðgerðir“ og hélt áfram.'
        sentences = strip_markdown_formatting(text, protect_quotes=False)
        texts = [s[0] for s in sentences]
        assert any("Við þurfum aðgerðir" in t for t in texts)


# ── _strip_direct_quotes ──────────────────────────────────────


class TestStripDirectQuotes:
    def test_strips_icelandic_quotes(self):
        result = _strip_direct_quotes("Hann sagði „þetta er rétt“ í dag.")
        assert "þetta er rétt" not in result
        assert "Hann sagði" in result

    def test_strips_angle_quotes(self):
        result = _strip_direct_quotes("Hún sagði «þetta er rangt» í gær.")
        assert "þetta er rangt" not in result
        assert "Hún sagði" in result

    def test_multiple_quotes(self):
        result = _strip_direct_quotes("„Fyrst“ og „síðan“.")
        assert "Fyrst" not in result
        assert "síðan" not in result

    def test_ascii_closing_quote(self):
        # Real-world pattern: „ opens, ASCII " closes
        result = _strip_direct_quotes('Hann sagði „þetta er rétt" í dag.')
        assert "þetta er rétt" not in result
        assert "Hann sagði" in result

    def test_no_quotes_unchanged(self):
        text = "Engar tilvitnarnir hér."
        assert _strip_direct_quotes(text) == text


# ── strip_direct_quotes_keep_lines (line-number-preserving variant) ──


class TestStripDirectQuotesKeepLines:
    """Quote-stripping must preserve line numbers so downstream flag-only
    layers report accurate L### output even below multi-line verbatim quotes."""

    def test_preserves_line_count_single_line_quote(self):
        content = 'Lína eitt.\nRáðherra sagði „eitthvað hér” í dag.\nLína þrjú.'
        out = strip_direct_quotes_keep_lines(content)
        assert out.count("\n") == content.count("\n")
        assert "eitthvað hér" not in out
        assert "Ráðherra sagði" in out
        assert "Lína eitt" in out and "Lína þrjú" in out

    def test_preserves_line_count_multiline_quote(self):
        # A quote spanning a newline must not collapse downstream line numbers.
        content = 'Fyrir.\nHann sagði „þetta er\nlöng tilvitnun” og hætti.\nEftir.'
        out = strip_direct_quotes_keep_lines(content)
        assert out.count("\n") == content.count("\n")
        assert "löng tilvitnun" not in out
        assert "Eftir." in out

    def test_text_without_quotes_unchanged(self):
        content = "Engar tilvitnanir hér, bara texti."
        assert strip_direct_quotes_keep_lines(content) == content


# ── tweets_json_to_text ────────────────────────────────────────


class TestTweetsJsonToText:
    def test_daily_format(self, tmp_path):
        f = tmp_path / "tweets.json"
        f.write_text(
            json.dumps(
                {"tweets": [{"text": "Fyrsta tíst."}, {"text": "Annað tíst."}]},
                ensure_ascii=False,
            )
        )
        out = tweets_json_to_text(f)
        assert "Tíst 1: Fyrsta tíst." in out
        assert "Tíst 2: Annað tíst." in out

    def test_weekly_format_thread_and_quotes(self, tmp_path):
        f = tmp_path / "tweets.json"
        f.write_text(
            json.dumps(
                {
                    "thread": [{"text": "Þráður eitt."}],
                    "quotes": [{"text": "Tilvitnun ein."}],
                },
                ensure_ascii=False,
            )
        )
        out = tweets_json_to_text(f)
        assert "Tíst 1: Þráður eitt." in out
        assert "Tilvitnun 1: Tilvitnun ein." in out


# ── graceful-degradation guard (no tokenizer) ──────────────────


def test_strip_markdown_without_tokenizer_falls_back_to_lines():
    """Preserved guard: when the optional ``tokenizer`` package is unavailable,
    strip_markdown_formatting must fall back to one (cleaned-line, line-number)
    entry per line rather than raising — the ``try/except ImportError``
    degradation. Patching ``_HAS_TOKENIZER`` to False simulates the absence.
    """
    text = "Fyrsta lína hér. Önnur setning sama lína.\n\nÞriðja lína hér."
    with patch("ispipeline.preprocessing._HAS_TOKENIZER", False):
        out = strip_markdown_formatting(text)
    # Fallback yields one entry per non-empty cleaned line (no sentence split),
    # so the two sentences on line 1 stay a single entry.
    assert out == [
        ("Fyrsta lína hér. Önnur setning sama lína.", 1),
        ("Þriðja lína hér.", 3),
    ]
