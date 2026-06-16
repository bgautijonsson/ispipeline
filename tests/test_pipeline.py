"""Tests for the ispipeline composition seam (pipeline.py + the public API).

These exercise the integration layer the merge-Workflow did not write. They run
on the pure-stdlib layers (confusables, register, eu_terms, preprocessing) so
they pass with or without the ``icelandic`` extra; the GreynirCorrect / BÍN /
Icegrams layers simply degrade to empty results when those deps are absent.
"""

from __future__ import annotations

import pytest

import ispipeline
from ispipeline import correct_icelandic, run_all_checks
from ispipeline.pipeline import apply_corrections


def test_package_imports_and_version():
    assert ispipeline.__version__ == "0.1.0"
    # the high-level seam and a representative layer fn are both re-exported
    assert callable(ispipeline.correct_icelandic)
    assert callable(ispipeline.check_confusables)


def test_check_mode_returns_list_of_tagged_issues():
    issues = correct_icelandic("Texti um aðildarviðræður.", mode="check")
    assert isinstance(issues, list)
    assert all("layer" in i for i in issues)


def test_check_mode_flags_ascii_transliteration_via_confusables():
    # "adildar"/"thjodar" are ASCII-transliterated Icelandic — the confusables
    # layer (pure stdlib, always on) must flag this regardless of the extra.
    issues = correct_icelandic("Their fjalla um adildar thjodar mali.", mode="check")
    layers = {i["layer"] for i in issues}
    assert "confusables" in layers


def test_full_mode_returns_str_and_is_idempotent_on_clean_text():
    clean = "Þetta er hreinn texti án villna."
    out = correct_icelandic(clean, mode="full")
    assert isinstance(out, str)
    # normalise_typography is a no-op on already-correct text → unchanged
    assert correct_icelandic(out, mode="full") == out


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        correct_icelandic("x", mode="bogus")


def test_domain_layer_register_is_opt_in():
    text = "Þetta var algjör djók og stressað mál."  # register borrowings
    without = run_all_checks(text)
    assert "register" not in without
    with_register = run_all_checks(text, layers=["register"])
    assert "register" in with_register and "compounds" in with_register
    # the borrowings ("djók", "stressað") are flagged by the register layer
    assert len(with_register["register"]) >= 1


def test_core_layers_always_present():
    results = run_all_checks("Stutt setning hér.")
    # greynir + confusables + heuristics always run (even if greynir degrades to [])
    assert "greynir" in results
    assert "confusables" in results
    assert "heuristics" in results


def test_apply_corrections_reports_fix_count_type():
    corrected, n = apply_corrections("Halló heimur.")
    assert isinstance(corrected, str)
    assert isinstance(n, int)


def test_malfridur_layer_degrades_without_transport(monkeypatch):
    # No MALSTADUR_API_KEY / httpx call should happen during a plain check run;
    # the malfridur layer must degrade to [] rather than raising.
    monkeypatch.delenv("MALSTADUR_API_KEY", raising=False)
    results = run_all_checks("Stutt setning.", layers=["malfridur"])
    assert results.get("malfridur") == []
