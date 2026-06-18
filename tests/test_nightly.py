"""Tests for the nightly estate-health wrapper's pure logic."""

from __future__ import annotations

import json

from ispipeline import nightly


def _rows(detail: str):
    return [("health:frettasafn", "WARN", detail)]


def test_stale_sources_parses_stale_tokens():
    detail = (
        "political  (stale at >7d)\n"
        "  [STALE]  vg                  99.9d\n"
        "  [ok   ]  vidreisn             2.2d\n"
        "  [STALE]  bondi               96.8d\n"
    )
    assert nightly.stale_sources(_rows(detail)) == {"vg", "bondi"}


def test_stale_sources_empty_when_none_flagged():
    assert nightly.stale_sources(_rows("[ok   ]  visir  20m")) == set()


def test_first_run_has_no_prior_so_nothing_is_newly_stale(tmp_path):
    state = tmp_path / "s.json"
    assert nightly.load_prior_stale(state) is None  # no file yet → baseline, don't alert
    nightly.save_stale(state, {"vg", "bondi"})
    assert nightly.load_prior_stale(state) == {"vg", "bondi"}


def test_newly_stale_is_the_set_difference(tmp_path):
    state = tmp_path / "s.json"
    nightly.save_stale(state, {"vg", "bondi"})          # chronic
    prior = nightly.load_prior_stale(state)
    current = {"vg", "bondi", "ruv"}                     # ruv (mainline) just broke
    assert current - prior == {"ruv"}                   # only the new break would notify


def test_save_stale_writes_sorted_json(tmp_path):
    state = tmp_path / "nested" / "s.json"
    nightly.save_stale(state, {"b", "a"})
    assert json.loads(state.read_text())["stale"] == ["a", "b"]


def test_append_log_creates_then_appends(tmp_path):
    log = tmp_path / "Estate Health Log.md"
    counts = {"OK": 3, "WARN": 1, "FAIL": 0}
    nightly.append_log(log, "2026-06-18 08:00", "WARN", counts, "report-one")
    nightly.append_log(log, "2026-06-19 08:00", "OK", {"OK": 4, "WARN": 0, "FAIL": 0}, "report-two")
    text = log.read_text()
    assert text.startswith("# Estate Health Log")      # header written once
    assert text.count("# Estate Health Log") == 1
    assert "report-one" in text and "report-two" in text
    assert "2026-06-18 08:00 — WARN (3 OK · 1 WARN · 0 FAIL)" in text
