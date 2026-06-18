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
repo pins which package, and where). The intended future home of these is a
nightly estate health-monitor workflow.

## Status

`v0.1.3` — corrections extraction shipped + adopted by esbvaktin & althingi;
estate pin guard + on-demand health monitor added. See
`docs/plans/2026-06-16-ispipeline-extraction.md`.
