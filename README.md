# ispipeline

Shared Icelandic text-correction pipeline for the Metill civic-tech estate
([esbvaktin](https://github.com/bgautijonsson/esbvaktin),
[althingi/Þingfréttir](https://thingfrettir.is), frettasafn).

It consolidates two forks of the same `corrections/` tree — esbvaktin's
(civic/EU register) and althingi's (parliamentary register) — that had drifted
~380 LOC apart, into one library with a single API and a shared quality gate.

## Why

esbvaktin and althingi independently grew the *same* eight-layer Icelandic
correction stack (GreynirCorrect → confusables → inflections → naturalness, plus
domain layers). Each repo evolved guards the other lacked — esbvaktin a `SIGALRM`
hang-guard and ASCII-transliteration detection, althingi an in-quote guard.
`ispipeline` is the **union** of both, kept honest by the shared
[iseval](https://github.com/bgautijonsson/iseval) harness: a consumer's
correction quality (false-positive rate over goldens + voice heuristics) must not
regress when it swaps its local `corrections/` for this package.

## Install

```bash
# editable, for local dev
uv pip install -e "/path/to/ispipeline[icelandic]"

# pinned by git ref (the iseval pattern), in a consumer's pyproject
"ispipeline @ git+https://github.com/bgautijonsson/ispipeline.git@v0.1.0"
```

The bare package imports with no third-party deps; the `icelandic` extra pulls
`reynir-correct`, `icegrams`, `islenska`, `reynir`.

## Use

```python
from ispipeline import correct_icelandic

# full deterministic correction, civic-register layers
fixed = correct_icelandic(text, mode="full", layers=["eu_terms", "malfridur"])

# check-only (return flagged issues, change nothing)
issues = correct_icelandic(text, mode="check", layers=["ministers", "register"])
```

Layers: `eu_terms`, `malfridur` (civic/EU) · `ministers`, `register`,
`preprocessing` (parliamentary). The deterministic core
(greynir/confusables/inflections/naturalness/parsing) always runs.

## Layout

```
src/ispipeline/
  greynir.py        GreynirCorrect grammar/spelling (union of both guards)
  confusables.py    LLM confusable-word scanner + ASCII detection
  inflections.py    BÍN inflection validation
  naturalness.py    Icegrams trigram scoring + heuristic checks
  parsing.py        GreynirEngine deep CFG parse
  eu_terms.py       EU terminology consistency        [civic layer]
  malfridur.py      Málfríður style fixes              [civic layer]
  ministers.py      Minister-portfolio fact-check      [parliamentary layer]
  register.py       Formal-register borrowing scanner  [parliamentary layer]
  preprocessing.py  Markdown/tweets normalisation
  cli.py            CLI entry point + orchestration
  pipeline.py       correct_icelandic() composition seam
```

## Eval gate

Consumers keep their own `eval/baseline.json` and iseval CI job. Adopting or
bumping `ispipeline` requires re-running the gate and re-baselining in the same
PR if a number legitimately moves. See each consumer's CLAUDE.md § "Eval gate".

## Estate ops tools

This repo also hosts two cross-repo estate tools (pure stdlib):

```bash
# Pin-drift guard — assert every consumer pins the same ref for each shared
# package (ispipeline + isretrieval). Catches a silent re-fork.
ispipeline-check-pins                 # all packages, all consumers
ispipeline-check-pins --package isretrieval

# Estate health monitor (on-demand) — pin guard + each repo's health script,
# aggregated to one PASS/WARN/FAIL report.
ispipeline-estate-health              # full report
ispipeline-estate-health --quiet      # only WARN/FAIL
```

`src/ispipeline/check_pins.py` carries the `PACKAGE_CONSUMERS` registry (which
repo pins which package, and where). `ispipeline-estate-health` is wired to run
nightly via launchd (`is.metill.estate-health`, see `scripts/`).

## Updating a shared package

The point of the git-ref-pin pattern is that a package change can't reach a
consumer until that consumer re-pins **and re-proves** it. The loop, end to end —
do it once per package bump and no rediscovery is needed:

1. **Change + tag the package.** Make the change in `ispipeline`/`isretrieval`,
   extend its tests (add a *golden* for behaviour-preserving changes), then:

   ```bash
   uv run pytest && ruff check .
   git commit -am "…" && git tag v0.1.4 && git push origin master --tags
   ```

2. **Re-pin each consumer** of that package (registry below). Two pin syntaxes
   are in use — bump whichever the repo uses, to the new tag:
   - PEP 508 direct ref (esbvaktin): `"ispipeline @ git+https://….git@v0.1.4"`
   - `[tool.uv.sources]` tag (althingi-content, althingi-mcp, frettasafn):
     `ispipeline = { git = "https://….git", tag = "v0.1.4" }`

   Then `uv sync` (esbvaktin needs `--extra icelandic --extra eval --extra dev`
   to pull the gate + test deps).

3. **Re-prove behaviour in each consumer** — this is the safety net, not optional:
   - **ispipeline consumers** re-run the iseval gate (the free
     behaviour-preservation proof):

     ```bash
     uv run python -m iseval gate --product <p> --family correction \
       --adapter eval.iseval_adapter:<Adapter> --golden eval/golden \
       --baseline eval/baseline.json --gate-config eval/gate.json
     ```

     Numbers hold → done. A number moved *legitimately* → re-baseline in the
     **same commit** with the delta explained. **Never widen `gate.json` to dodge
     a regression** — that throws away the whole proof.
   - **isretrieval consumers** re-run the RRF golden tests (rankings must be
     byte-identical): `pytest tests/test_rrf_merge.py` (esbvaktin),
     `pytest tests/test_rrf_fusion.py` (althingi root, frettasafn).

4. **Drift-check + health**, from this repo:

   ```bash
   ispipeline-check-pins        # every consumer pins the same ref per package
   ispipeline-estate-health     # pin guard + each repo's health
   ```

5. **Commit + merge** each consumer (fast-forward to its default branch) and push.

### Consumer registry

| Package | Consumers — pin location |
|---|---|
| `ispipeline` | esbvaktin (`pyproject.toml`) · althingi-content (`pyproject.toml` `[tool.uv.sources]`) |
| `isretrieval` | esbvaktin · althingi-mcp · frettasafn |
| `iseval` | esbvaktin · althingi (`eval` extra / group) |

Authoritative copy: `src/ispipeline/check_pins.py::PACKAGE_CONSUMERS`.

**Local gotchas** (verified — they bite every time):
- The gate needs the eval deps synced first, or you get `No module named iseval`
  → `uv sync --group eval` (althingi) / `--extra eval` (esbvaktin).
- esbvaktin's `pytest` lives in its `dev` extra — sync it to run tests locally.
- `ispipeline-estate-health` exits **0 even on WARN** (only FAIL is non-zero) —
  parse the report line, don't trust the exit code.

## Status

`v0.1.3` — corrections extraction shipped + adopted by esbvaktin & althingi;
estate pin guard + on-demand health monitor added. See
`docs/plans/2026-06-16-ispipeline-extraction.md`.
