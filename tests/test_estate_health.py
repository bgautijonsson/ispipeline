"""Tests for the estate health monitor's pure aggregation/rendering logic.

The subprocess orchestration (run_repo_health) and the pin-guard wiring are
verified by actually running ``ispipeline-estate-health``; here we pin down the
status roll-up and report formatting, which is where the logic lives.
"""

from __future__ import annotations

from ispipeline.estate_health import FAIL, OK, WARN, render, summarise


def test_summarise_all_ok():
    rows = [("pins:ispipeline", OK, ""), ("health:frettasafn", OK, "")]
    overall, counts = summarise(rows)
    assert overall == OK
    assert counts == {OK: 2, WARN: 0, FAIL: 0}


def test_summarise_warn_beats_ok():
    rows = [("a", OK, ""), ("b", WARN, "")]
    assert summarise(rows)[0] == WARN


def test_summarise_fail_beats_warn():
    rows = [("a", OK, ""), ("b", WARN, ""), ("c", FAIL, "")]
    overall, counts = summarise(rows)
    assert overall == FAIL
    assert counts == {OK: 1, WARN: 1, FAIL: 1}


def test_render_header_and_fail_row():
    rows = [("pins:isretrieval", FAIL, "DRIFT: consumers pin DIFFERENT refs")]
    out = render(rows)
    assert "Metill estate health: FAIL" in out
    assert "[FAIL] pins:isretrieval" in out
    assert "DRIFT" in out


def test_render_quiet_hides_ok_rows():
    rows = [("pins:ispipeline", OK, "OK: all pin v0.1.0"), ("health:althingi", WARN, "stale")]
    out = render(rows, quiet=True)
    assert "pins:ispipeline" not in out  # OK row hidden
    assert "[WARN] health:althingi" in out
    assert "stale" in out


def test_render_indents_detail_lines():
    rows = [("health:frettasafn", WARN, "line one\nline two")]
    out = render(rows)
    assert "        line one" in out
    assert "        line two" in out
