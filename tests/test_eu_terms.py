"""Smoke + guard tests for the eu_terms civic layer (ported verbatim from esbvaktin).

No tests existed in either fork's test tree for these public functions; these
exercise each warning category check_eu_terms emits and assert the preserved
guards (English-term mapping, missing-hyphen detection, LLM-hallucination
pattern, document-level inconsistency detection) actually fire.
"""

from ispipeline.eu_terms import check_eu_terms, format_eu_term_results


def test_english_term_flagged():
    """An English EU term in Icelandic text is flagged with its Icelandic suggestion."""
    warnings = check_eu_terms("Hér er talað um Common Fisheries Policy í greininni.")
    eng = [w for w in warnings if w["type"] == "english_term"]
    assert any(w["found"] == "Common Fisheries Policy" for w in eng)
    assert any(w["suggestion"] == "sameiginleg sjávarútvegsstefna" for w in eng)


def test_missing_hyphen_guard_fires():
    """The missing-hyphen guard catches 'ESB aðild' and suggests the hyphenated form."""
    warnings = check_eu_terms("Umræðan snýst um ESB aðild Íslands.")
    hyphen = [w for w in warnings if w["type"] == "missing_hyphen"]
    assert hyphen, "missing_hyphen guard did not fire on 'ESB aðild'"
    assert "bandstrik vantar" in hyphen[0]["suggestion"]


def test_wrong_translation_hallucination_guard():
    """The LLM-hallucination guard flags a bad 'Haag-viðmiðin' rendering."""
    warnings = check_eu_terms("Þetta varðar háguþkjörgæði samkvæmt samningnum.")
    wrong = [w for w in warnings if w["type"] == "wrong_translation"]
    assert wrong, "wrong_translation guard did not fire"
    assert wrong[0]["suggestion"] == "Haag-viðmiðin"


def test_inconsistent_variant_pair_is_document_level():
    """Mixing a preferred term and its variant yields a document-level (line 0) warning."""
    text = "Við ræðum Evrópusambandið en líka Evrópubandalagið í sama texta."
    warnings = check_eu_terms(text)
    inconsistent = [w for w in warnings if w["type"] == "inconsistent"]
    assert inconsistent, "inconsistent-variant guard did not fire"
    assert inconsistent[0]["line"] == 0


def test_clean_text_yields_no_warnings():
    """Plain Icelandic with no EU-term issues produces no warnings."""
    assert check_eu_terms("Þetta er venjulegur íslenskur texti um veðrið.") == []


def test_format_returns_count(capsys):
    """format_eu_term_results returns the warning count and prints the clean line when empty."""
    assert format_eu_term_results([], "skra.md") == 0
    out = capsys.readouterr().out
    assert "EU terminology consistent" in out

    warnings = check_eu_terms("Common Fisheries Policy")
    assert format_eu_term_results(warnings, "skra.md") == len(warnings)
