"""Smoke + guard tests for ispipeline.malfridur.

No tests existed in either fork (esbvaktin/althingi) for the malfridur public
functions, so these are minimal: exercise the pure-string helpers on a tiny
Icelandic string, and assert the preserved graceful-degradation guard fires
(check_with_malfridur raises ImportError when the Málstaður transport client is
unavailable, rather than crashing at module import).
"""

import builtins

import pytest

from ispipeline.malfridur import (
    apply_malfridur_fixes,
    apply_malfridur_fixes_to_file,
    check_with_malfridur,
    format_malfridur_results,
)


def _result(line, original, corrected, *, auto_fixable=True, annotations=None):
    return {
        "line": line,
        "original": original,
        "corrected": corrected,
        "annotations": annotations or [],
        "auto_fixable": auto_fixable,
    }


# ── Pure-string helpers (no third-party deps) ─────────────────────────────


def test_apply_malfridur_fixes_replaces_once():
    text = "Þetta er gott. Þetta er gott."
    results = [_result(1, "Þetta er gott.", "Þetta er frábært.")]
    out, fixes = apply_malfridur_fixes(text, results)
    assert fixes == 1
    # Only the first occurrence is replaced (count=1 in str.replace).
    assert out == "Þetta er frábært. Þetta er gott."


def test_apply_malfridur_fixes_skips_non_auto_fixable():
    text = "Halló heimur."
    results = [_result(1, "Halló heimur.", "Sæll heimur.", auto_fixable=False)]
    out, fixes = apply_malfridur_fixes(text, results)
    assert fixes == 0
    assert out == text


def test_apply_malfridur_fixes_skips_when_original_absent():
    text = "Góðan daginn."
    results = [_result(1, "Ekki í texta", "Eitthvað annað")]
    out, fixes = apply_malfridur_fixes(text, results)
    assert fixes == 0
    assert out == text


def test_apply_malfridur_fixes_to_file_writes_and_backs_up(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("Þetta er villa.", encoding="utf-8")
    results = [_result(1, "Þetta er villa.", "Þetta er rétt.")]
    fixes = apply_malfridur_fixes_to_file(f, results)
    assert fixes == 1
    assert f.read_text(encoding="utf-8") == "Þetta er rétt."
    # A .bak copy of the original is created when fixes are applied.
    bak = f.with_suffix(f.suffix + ".bak")
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == "Þetta er villa."


def test_apply_malfridur_fixes_to_file_no_changes_no_backup(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("Allt í lagi.", encoding="utf-8")
    results = [_result(1, "Ekki til staðar", "Skiptir ekki máli")]
    fixes = apply_malfridur_fixes_to_file(f, results)
    assert fixes == 0
    assert not f.with_suffix(f.suffix + ".bak").exists()


def test_format_malfridur_results_counts(capsys):
    results = [
        _result(
            3,
            "Þetta er villa.",
            "Þetta er rétt.",
            annotations=[
                {
                    "changeType": "spelling",
                    "origString": "villa",
                    "changedString": "rétt",
                }
            ],
        ),
        _result(5, "Allt í lagi.", "Allt í lagi.", auto_fixable=False),
    ]
    corrections, unchanged = format_malfridur_results(results, "skjal.md")
    assert (corrections, unchanged) == (1, 1)
    out = capsys.readouterr().out
    assert "[FIX]" in out
    assert "spelling" in out


def test_format_malfridur_results_no_corrections(capsys):
    results = [_result(1, "Texti.", "Texti.", auto_fixable=False)]
    corrections, unchanged = format_malfridur_results(results, "skjal.md")
    assert (corrections, unchanged) == (0, 1)
    assert "No corrections needed" in capsys.readouterr().out


# ── Transport-dependent path ──────────────────────────────────────────────


def test_check_with_malfridur_empty_short_circuits():
    # Empty input returns [] without touching the transport client at all.
    assert check_with_malfridur([]) == []


def test_check_with_malfridur_import_guard_fires(monkeypatch):
    """Preserved guard: when the Málstaður transport client is unavailable,
    check_with_malfridur raises ImportError (lazy import) rather than failing
    at module import time."""
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "ispipeline.malstadur" or name.endswith(".malstadur"):
            raise ImportError("simulated: malstadur transport unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    with pytest.raises(ImportError):
        check_with_malfridur([("Halló heimur.", 1)])
