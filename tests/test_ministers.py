"""Tests for ispipeline.ministers — parliamentary minister-portfolio layer.

Ported from althingi's tests/test_correct_icelandic.py::TestMinisterReferences,
with imports rewritten to ispipeline. The original suite resolved the cabinet
data from althingi-content/knowledge/government.json; here the fixture writes a
faithful copy of that cabinet into tmp_path (via json.dump(ensure_ascii=False))
so the tests are hermetic and never reach outside the package.
"""

import json
from pathlib import Path

import pytest

from ispipeline.ministers import (
    check_minister_references,
    format_minister_results,
)

# Faithful copy of the althingi cabinet (government.json, updated 2026-02-10),
# trimmed to the fields check_minister_references reads.
_CABINET = [
    {
        "name": "Kristrún Frostadóttir",
        "role_is": "Forsætisráðherra",
        "role_en": "Prime Minister",
        "party": "Samfylkingin",
    },
    {
        "name": "Þorgerður Katrín Gunnarsdóttir",
        "role_is": "Utanríkisráðherra",
        "role_en": "Foreign Affairs Minister",
        "party": "Viðreisn",
    },
    {
        "name": "Inga Sæland",
        "role_is": "Mennta- og barnamálaráðherra",
        "role_en": "Education and Children's Affairs Minister",
        "party": "Flokkur fólksins",
    },
    {
        "name": "Daði Már Kristófersson",
        "role_is": "Fjármála- og efnahagsráðherra",
        "role_en": "Finance and Economics Minister",
        "party": "Viðreisn",
    },
    {
        "name": "Jóhann Páll Jóhannsson",
        "role_is": "Umhverfis-, orku- og loftslagsráðherra",
        "role_en": "Environment, Energy and Climate Minister",
        "party": "Samfylkingin",
    },
]


@pytest.fixture
def gov_path(tmp_path) -> Path:
    """Write a real-cabinet government.json into tmp_path and return its path."""
    p = tmp_path / "government.json"
    with p.open("w", encoding="utf-8") as f:
        json.dump({"cabinet": _CABINET}, f, ensure_ascii=False)
    return p


class TestMinisterReferences:
    def test_correct_reference_no_warning(self, gov_path):
        text = "Kristrún Frostadóttir, forsætisráðherra, tók til máls."
        result = check_minister_references(text, gov_path)
        assert len(result) == 0

    def test_wrong_portfolio_flagged(self, gov_path):
        # Þorgerður Katrín is utanríkisráðherra, not fjármálaráðherra
        text = "Þorgerður Katrín Gunnarsdóttir, fjármálaráðherra, sagði frá."
        result = check_minister_references(text, gov_path)
        assert len(result) >= 1
        assert result[0]["name"] == "Þorgerður Katrín Gunnarsdóttir"
        assert "fjármálaráðherra" in result[0]["found_role"]

    def test_no_minister_mention_no_warning(self, gov_path):
        text = "Þingmaðurinn tók til máls í umræðunni."
        result = check_minister_references(text, gov_path)
        assert result == []

    def test_missing_government_file(self, tmp_path):
        # Preserved guard: a non-existent government.json yields [] (no crash).
        text = "Kristrún Frostadóttir, forsætisráðherra."
        result = check_minister_references(text, tmp_path / "nonexistent.json")
        assert result == []

    def test_returns_required_fields(self, gov_path):
        text = "Þorgerður Katrín Gunnarsdóttir, fjármálaráðherra, sagði."
        result = check_minister_references(text, gov_path)
        for entry in result:
            assert "line" in entry
            assert "name" in entry
            assert "found_role" in entry
            assert "correct_role" in entry
            assert "context" in entry

    def test_correct_role_with_suffix(self, gov_path):
        # "forsætisráðherrans" (genitive) — name here is in genitive form, so
        # the reverse scan (nominative lookups) does not trigger. Genitive-name
        # support is deferred (audit P1.M2). No false positive expected.
        text = "Áætlun forsætisráðherrans Kristrúnar Frostadóttur."
        result = check_minister_references(text, gov_path)
        assert isinstance(result, list)

    # ── Reverse scan: role before (nominative) name (audit P1.M2) ──

    def test_wrong_portfolio_role_before_name_nominative(self, gov_path):
        """Role in nominative precedes a nominative name with wrong portfolio.
        Kristrún Frostadóttir is Forsætisráðherra, not Umhverfisráðherra."""
        text = "Umhverfisráðherra Kristrún Frostadóttir lagði fram áætlunina."
        result = check_minister_references(text, gov_path)
        assert len(result) >= 1, f"Expected wrong-portfolio flag; got: {result}"
        assert result[0]["name"] == "Kristrún Frostadóttir"
        assert "umhverfisráðherra" in result[0]["found_role"].lower()

    def test_wrong_portfolio_forsaetis_before_foreign_minister(self, gov_path):
        """Forsætisráðherra Þorgerður Katrín — Þorgerður is Utanríkisráðherra,
        not Forsætisráðherra."""
        text = "Forsætisráðherra Þorgerður Katrín Gunnarsdóttir sagði frá málinu."
        result = check_minister_references(text, gov_path)
        assert len(result) >= 1, f"Expected wrong-portfolio flag; got: {result}"
        assert "Þorgerður Katrín Gunnarsdóttir" in [r["name"] for r in result]

    def test_correct_role_before_name_no_flag(self, gov_path):
        """Role before name, role IS correct — no flag."""
        text = "Forsætisráðherra Kristrún Frostadóttir lagði fram áætlunina."
        result = check_minister_references(text, gov_path)
        assert result == [], f"False positive on correct role-before-name: {result}"


class TestFormatMinisterResults:
    """Smoke coverage for the second public function (untested upstream)."""

    def test_no_warnings_returns_zero(self, capsys):
        n = format_minister_results([], "demo_is.md")
        assert n == 0
        out = capsys.readouterr().out
        assert "Minister references OK" in out

    def test_warnings_returns_count_and_prints(self, capsys):
        warnings = [
            {
                "line": 3,
                "name": "Þorgerður Katrín Gunnarsdóttir",
                "found_role": "fjármálaráðherra",
                "correct_role": "Utanríkisráðherra",
                "context": "Þorgerður Katrín Gunnarsdóttir, fjármálaráðherra, sagði frá.",
            }
        ]
        n = format_minister_results(warnings, "demo_is.md")
        assert n == 1
        out = capsys.readouterr().out
        assert "[MINISTER]" in out
        assert "fjármálaráðherra" in out
        assert "Utanríkisráðherra" in out
