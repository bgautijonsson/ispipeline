# ispipeline Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the two forked Icelandic `corrections/` trees (esbvaktin + althingi) into one git-ref-pinned package, `ispipeline`, proven behaviour-preserving by the shared iseval gate at adoption time.

**Architecture:** A `src`-layout, hatchling-built Python package mirroring iseval's conventions. Each correction layer is a module; the deterministic core always runs; domain layers (`eu_terms`/`malfridur` for civic, `ministers`/`register` for parliamentary) are opt-in via a `layers=` argument. The merge strategy is **union, not pick-a-winner**: every guard either fork evolved is preserved, and iseval tells us at adoption time whether the union regresses either register.

**Tech Stack:** Python ≥3.11, hatchling, `reynir-correct`/`icegrams`/`islenska`/`reynir` (optional `icelandic` extra), pytest, iseval (consumer-side gate).

---

## Source inventory

| Module | esbvaktin LOC | althingi LOC | Merge base | Notes |
|---|---|---|---|---|
| `greynir.py` | 232 | 233 | union | esbvaktin: `SIGALRM` hang-guard, graceful `ImportError`, ASCII detection, `apply_fixes_to_text`. althingi: in-quote guard. Keep ALL. |
| `confusables.py` | 179 | 116 | union | union the `CONFUSABLE_PATTERNS` tables (bíður/býður ∪ stuttur/grunur …); dedupe. |
| `inflections.py` | 92 | 125 | union | BÍN validation; reconcile `_extract_words`. |
| `naturalness.py` | 267 | 242 | esbvaktin superset | esbvaktin has `run_heuristic_checks` + `check_hedging`/`check_missing_icelandic_chars`/`check_monotonous_openings`/`check_overformal_register` that althingi lacks (the "dormant" heuristics). Keep esbvaktin's; verify althingi's `score_naturalness` matches. |
| `parsing.py` | 63 | 61 | either (near-identical) | deep CFG parse; `_HAS_GREYNIR` guard. |
| `eu_terms.py` | 145 | — | civic layer | port verbatim. |
| `malfridur.py` | 124 | — | civic layer | port verbatim. |
| `ministers.py` | — | 123 | parliamentary layer | port verbatim. |
| `register.py` | — | 126 | parliamentary layer | port verbatim. |
| `preprocessing.py` | — | 231 | shared infra | markdown/tweets normalisation; port verbatim (both consumers can use). |
| `cli.py` | 601 | 466 | rebuild | both are orchestration; do NOT union blindly — rebuild a clean `cli.py` over the merged modules (see Task C2). |

**Union of public exports** (the `__init__` surface to preserve for near-drop-in swaps): `CONFUSABLE_PATTERNS, check_confusables, format_confusable_results, check_eu_terms, format_eu_term_results, AUTO_FIX_CODES, PHRASE_FIX_CODES, apply_fixes, apply_fixes_to_text, check_with_api, check_with_library, format_results, _HAS_ISLENSKA, _extract_words, check_inflections, format_inflection_results, apply_malfridur_fixes, apply_malfridur_fixes_to_file, check_with_malfridur, format_malfridur_results, _HAS_ICEGRAMS, check_hedging, check_missing_icelandic_chars, check_monotonous_openings, check_overformal_register, format_heuristic_results, format_naturalness_results, run_heuristic_checks, score_naturalness, _HAS_GREYNIR, deep_parse, format_deep_parse_results, strip_markdown_formatting, tweets_json_to_text, check_minister_references, format_minister_results, REGISTER_BLOCKLIST, check_register, format_register_results, check_compound_length, format_compound_results`.

---

## Target file structure

```
ispipeline/
  pyproject.toml            ✅ scaffolded
  README.md                 ✅ scaffolded
  .gitignore                ✅ scaffolded
  src/ispipeline/
    __init__.py             union re-exports + correct_icelandic
    greynir.py confusables.py inflections.py naturalness.py parsing.py
    eu_terms.py malfridur.py ministers.py register.py preprocessing.py
    pipeline.py             correct_icelandic(text, mode, layers) seam
    cli.py                  argparse entry point
  tests/
    test_<module>.py        ported from both repos + merge-specific tests
  data/golden/              shared smoke goldens (optional)
```

---

## Phase 1 — Build the `ispipeline` package (this session)

### Task 0: Scaffold — DONE
- [x] dirs, `pyproject.toml`, `README.md`, `.gitignore`, `src/ispipeline/__init__.py` (version stub), `git init`.

### Task M1–M5: Merge the deterministic core (one task per module: greynir, confusables, inflections, naturalness, parsing)

For each module, the worker (or merge-Workflow agent):
- [ ] Read **both** forks (`esbvaktin/src/esbvaktin/corrections/<m>.py` and `althingi/althingi-content/corrections/<m>.py`) and both repos' tests touching it.
- [ ] Write `src/ispipeline/<m>.py` as the **union** per the table above — preserve every guard, dedupe shared tables, keep the superset of public functions.
- [ ] Port the existing tests from both repos into `tests/test_<m>.py`; add a merge-specific test proving a guard that only one fork had still fires (e.g. esbvaktin ASCII detection AND althingi in-quote skip both hold).
- [ ] `uv run --extra icelandic --group dev pytest tests/test_<m>.py -q` → PASS.

### Task L1: Port the domain layers verbatim
- [ ] Copy `eu_terms.py`, `malfridur.py` (from esbvaktin) and `ministers.py`, `register.py`, `preprocessing.py` (from althingi) into `src/ispipeline/`, fixing imports to `ispipeline.<m>`.
- [ ] Port their tests.

### Task C1: `pipeline.py` — the composition seam
- [ ] Implement `correct_icelandic(text: str, *, mode: str = "full", layers: list[str] | None = None) -> str | list`. `mode="full"` applies fixes and returns corrected text; `mode="greynir-only"` runs only the GreynirCorrect layer; `mode="check"` returns a list of flagged issues without mutating. `layers` selects opt-in domain layers (default: none → deterministic core only).
- [ ] Test: civic call (`layers=["eu_terms"]`) and parliamentary call (`layers=["ministers"]`) each run without importing the other layer's data; check-mode mutates nothing.

### Task C2: `cli.py` — rebuilt over merged modules
- [ ] Rebuild a single argparse CLI exposing the same subcommands both repos relied on (grammar check, `--fix`, check-editorial/check-narrative file modes). Reconcile esbvaktin's `cli.py` (601 LOC) and althingi's (466 LOC). Map `ispipeline = "ispipeline.cli:main"` (already in pyproject).
- [ ] Smoke test: `uv run ispipeline --help` and a `--fix` round-trip on a fixture file.

### Task A1: Assemble `__init__.py`
- [ ] Re-export the full union surface (list above) so consumers can `from ispipeline import <fn>` as a near-drop-in for `from <repo>.corrections import <fn>`. Plus export `correct_icelandic`.
- [ ] `uv run python -c "import ispipeline; print(ispipeline.__version__)"` → `0.1.0`, no ImportError.

### Task V1: Verify the package end-to-end
- [ ] `uv venv && uv pip install -e ".[icelandic]" --group dev`
- [ ] `uv run --group dev pytest -q` → all PASS.
- [ ] `uv run ispipeline --help` works.
- [ ] Commit locally (`feat: ispipeline v0.1.0 — union extraction of esbvaktin+althingi corrections`).

### Task P1: Publish (GATED — confirm with user first; outward-facing)
- [ ] `gh repo create bgautijonsson/ispipeline --public --source ~/ispipeline --remote origin --push`
- [ ] `git tag v0.1.0 && git push origin v0.1.0`

---

## Phase 2 — esbvaktin adoption (separate session, gated)

> Run in the esbvaktin session. **Prove no regression with iseval before merging.**

1. [ ] Baseline: record current `eval/baseline.json` numbers (fp_rate ≈ 0.42, voice 0).
2. [ ] Pin: add `"ispipeline @ git+https://github.com/bgautijonsson/ispipeline.git@v0.1.0"` to the `icelandic` (or a new `pipeline`) extra in `pyproject.toml`; add the direct-ref allow in `[tool.uv]`.
3. [ ] **Find the real swap surface.** The repo-survey found NO `from esbvaktin.corrections import` sites — esbvaktin likely invokes `scripts/correct_icelandic.py` (CLI) and/or the agents call it. Grep for `correct_icelandic`, `corrections`, and the CLI subcommands; map every caller before deleting anything.
4. [ ] Swap imports `esbvaktin.corrections.*` → `ispipeline.*` (enable `layers=["eu_terms","malfridur"]`). Keep `src/esbvaktin/corrections/` until the gate is green, then delete.
5. [ ] Re-run the iseval gate (`uv run --extra icelandic --extra eval python -m iseval run … --out eval/baseline.json`). If numbers hold → done; if they move legitimately → re-baseline in the same PR with the delta explained. **Never widen `gate.json` to dodge a regression.**
6. [ ] CI green; commit.

## Phase 3 — althingi adoption (separate session, gated) + adjacent wins

1. [ ] Baseline (fp_rate ≈ 0.34).
2. [ ] Pin ispipeline in the root `pyproject.toml`'s `eval`/`icelandic` group; enable `layers=["ministers","register"]`.
3. [ ] Swap: althingi's surface is the `correct_icelandic.py` shim (`from corrections import *`) + `from corrections.preprocessing import …` + `from corrections.greynir import check_with_library` (in `weekly/validate_digest.py`, `posting/cli.py`). Point the shim at `ispipeline`.
4. [ ] Re-run iseval gate; re-baseline if a number legitimately moves.
5. [ ] **Adjacent win — live-wire dormant naturalness heuristics:** althingi's `naturalness.py` lacked `run_heuristic_checks` etc.; now available from ispipeline — wire them into althingi's `cli.py` check path.
6. [ ] **Adjacent win — exemplar-bank budget clause:** verify `.claude/agents/icelandic-writer.md:215` budget clause still silently blocks the exemplar bank (vs the `:56` mandate). If still broken, fix so the exemplar bank loads on real runs.
7. [ ] CI green; commit.

## Phase 4 — Pattern-F pin-drift guard
- [ ] Add a tiny check (CI or a shared health script) asserting esbvaktin and althingi pin the **same** `ispipeline@vX.Y.Z` ref — divergence here silently re-forks the pipeline.

---

## Parallel cheap wins (independent of ispipeline; do in the relevant repo's session)

- **althingi guard hook (Pattern C):** pre-publish guard on `publish_to_metill.py` — assert table counts ≥ prior manifest floor and do an atomic swap (temp → rename) instead of in-place S3 overwrite.
- **esbvaktin export Workflow (Pattern A):** convert `scripts/run_export.sh` into a saved DAG-parallel Workflow (entities ‖ evidence ‖ topics ‖ speeches → claims + prepare_site → build). `fresh-03` incremental export is already in place. This becomes the reusable Pattern-A template for the estate.

## Roadmap after ispipeline (same pattern, one at a time)
`isembeddings` (consolidate bge-m3 + fix althingi's O(n²) backfill) → `isretrieval` (RRF) → `iskeywords`/`isentity`/`istranslations` → capstone: a scheduled nightly estate health-monitor Workflow (Pattern E+F) that keeps every shared git-ref pin honest and catches cross-repo schema drift.
