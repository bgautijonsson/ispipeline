"""Tests for the pin-drift guard."""

from __future__ import annotations

from ispipeline.check_pins import check_pins, find_pin

PIN = "ispipeline @ git+https://github.com/bgautijonsson/ispipeline.git@v0.1.0"


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_find_pin_extracts_ref():
    assert find_pin(f'dependencies = ["{PIN}"]') == "v0.1.0"


def test_find_pin_in_optional_extra_and_group():
    extra = f'[project.optional-dependencies]\npipeline = [\n    "{PIN}",\n]\n'
    assert find_pin(extra) == "v0.1.0"
    group = f'[dependency-groups]\neval = ["{PIN}"]\n'
    assert find_pin(group) == "v0.1.0"


def test_find_pin_uv_sources_table():
    # althingi's form: a bare dep + a [tool.uv.sources] entry with tag=
    body = (
        'dependencies = ["ispipeline"]\n'
        "[tool.uv.sources]\n"
        'ispipeline = { git = "https://github.com/bgautijonsson/ispipeline.git", tag = "v0.1.0" }\n'
    )
    assert find_pin(body) == "v0.1.0"


def test_find_pin_uv_sources_rev_and_branch():
    assert find_pin('ispipeline = { git = "x", rev = "abc123" }') == "abc123"
    assert find_pin('ispipeline = { git = "x", branch = "main" }') == "main"


def test_two_formats_same_ref_do_not_drift(tmp_path):
    # esbvaktin (PEP 508) vs althingi (uv sources) — same ref, different syntax.
    a = _write(tmp_path, "esb.toml", f'deps = ["{PIN}"]')
    b = _write(
        tmp_path,
        "alt.toml",
        '[tool.uv.sources]\nispipeline = { git = "https://github.com/bgautijonsson/ispipeline.git", tag = "v0.1.0" }\n',
    )
    code, pins = check_pins({"esbvaktin": a, "althingi": b})
    assert code == 0
    assert pins == {"esbvaktin": "v0.1.0", "althingi": "v0.1.0"}


def test_find_pin_absent_returns_none():
    assert find_pin('dependencies = ["httpx>=0.27"]') is None


def test_matching_refs_pass(tmp_path):
    a = _write(tmp_path, "a.toml", f'deps = ["{PIN}"]')
    b = _write(tmp_path, "b.toml", f'deps = ["{PIN}"]')
    code, pins = check_pins({"a": a, "b": b})
    assert code == 0
    assert pins == {"a": "v0.1.0", "b": "v0.1.0"}


def test_diverging_refs_fail(tmp_path):
    a = _write(tmp_path, "a.toml", f'deps = ["{PIN}"]')
    b = _write(tmp_path, "b.toml", 'deps = ["ispipeline @ git+https://github.com/bgautijonsson/ispipeline.git@v0.2.0"]')
    code, pins = check_pins({"a": a, "b": b})
    assert code == 1
    assert pins["a"] == "v0.1.0" and pins["b"] == "v0.2.0"


def test_missing_pin_fails(tmp_path):
    a = _write(tmp_path, "a.toml", f'deps = ["{PIN}"]')
    b = _write(tmp_path, "b.toml", 'deps = ["httpx>=0.27"]')
    code, pins = check_pins({"a": a, "b": b})
    assert code == 1
    assert pins["b"] is None


def test_missing_file_fails(tmp_path):
    a = _write(tmp_path, "a.toml", f'deps = ["{PIN}"]')
    code, pins = check_pins({"a": a, "missing": str(tmp_path / "nope.toml")})
    assert code == 1
    assert pins["missing"] is None
