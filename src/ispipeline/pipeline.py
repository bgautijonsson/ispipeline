"""ispipeline.pipeline — the composition seam over the correction layers.

`run_all_checks` runs every applicable layer over a markdown document and
returns a structured result map (the programmatic form of the CLI).
`correct_icelandic` is the high-level convenience entry point.

Layer model:
  - Deterministic CORE always runs (register-neutral): typography, GreynirCorrect,
    confusables, inflections (if BÍN present), naturalness (if Icegrams present),
    heuristics, deep parse (if GreynirEngine present).
  - Opt-in DOMAIN layers, selected via ``layers=``:
      ``"eu_terms"``, ``"malfridur"``   -> civic / EU register
      ``"ministers"``, ``"register"``   -> parliamentary register

The split between ``sentences`` and ``quote_safe`` content matches the original
forks: sentence-level layers run on markdown-stripped, quote-protected text,
while line-scanning text layers run on content with verbatim „…" direct quotes
blanked (line count preserved) so we never flag words inside verbatim quotes.
"""

from __future__ import annotations

from pathlib import Path

from ispipeline.confusables import check_confusables
from ispipeline.eu_terms import check_eu_terms
from ispipeline.greynir import apply_fixes_to_text, check_with_api, check_with_library
from ispipeline.inflections import _HAS_ISLENSKA, check_inflections
from ispipeline.malfridur import apply_malfridur_fixes, check_with_malfridur
from ispipeline.ministers import check_minister_references
from ispipeline.naturalness import _HAS_ICEGRAMS, run_heuristic_checks, score_naturalness
from ispipeline.parsing import _HAS_GREYNIR, deep_parse
from ispipeline.preprocessing import (
    normalize_typography,
    strip_direct_quotes_keep_lines,
    strip_markdown_formatting,
)
from ispipeline.register import check_compound_length, check_register

DOMAIN_LAYERS = ("eu_terms", "malfridur", "ministers", "register")


def build_inputs(content: str) -> tuple[list[tuple[str, int]], str]:
    """Split raw markdown into ``(sentences, quote_safe_content)``."""
    sentences = strip_markdown_formatting(content)
    quote_safe = strip_direct_quotes_keep_lines(content)
    return sentences, quote_safe


def run_all_checks(
    content: str,
    *,
    layers: list[str] | None = None,
    threshold: float = 2.0,
    use_api: bool = False,
    deep: bool = True,
    government_path: Path | None = None,
) -> dict[str, object]:
    """Run every applicable layer; return ``{layer_name: results}``. Mutates nothing."""
    selected = set(layers or ())
    sentences, quote_safe = build_inputs(content)
    out: dict[str, object] = {}

    # --- deterministic core (always) ---
    check_fn = check_with_api if use_api else check_with_library
    out["greynir"] = check_fn(sentences) if sentences else []
    out["confusables"] = check_confusables(quote_safe)
    if _HAS_ISLENSKA:
        out["inflections"] = check_inflections(sentences)
    if _HAS_ICEGRAMS:
        out["naturalness"] = score_naturalness(sentences, threshold_sigma=threshold)
    out["heuristics"] = run_heuristic_checks(sentences)
    if deep and _HAS_GREYNIR:
        out["deep_parse"] = deep_parse(sentences)

    # --- opt-in domain layers ---
    if "eu_terms" in selected:
        out["eu_terms"] = check_eu_terms(quote_safe)
    if "ministers" in selected:
        out["ministers"] = check_minister_references(quote_safe, government_path)
    if "register" in selected:
        out["register"] = check_register(quote_safe)
        out["compounds"] = check_compound_length(quote_safe)
    if "malfridur" in selected:
        # API-based (paid, networked); degrade to [] if transport/key absent.
        try:
            out["malfridur"] = check_with_malfridur(sentences)
        except Exception:
            out["malfridur"] = []
    return out


def _flatten_issues(results: dict[str, object]) -> list[dict]:
    """Flatten the result map into issue dicts, each tagged with its ``layer``."""
    issues: list[dict] = []
    for layer, value in results.items():
        if isinstance(value, dict):  # run_heuristic_checks returns {check: [..]}
            for sub, items in value.items():
                for item in items:
                    issues.append({"layer": layer, "check": sub, **item})
        else:
            for item in value:  # type: ignore[union-attr]
                issues.append({"layer": layer, **item})
    return issues


def apply_corrections(
    text: str,
    *,
    layers: list[str] | None = None,
    use_api: bool = False,
    greynir: bool = True,
) -> tuple[str, int]:
    """Apply the auto-fixing layers in-memory; return ``(corrected_text, n_fixes)``.

    Only typography, GreynirCorrect, and the opt-in Málfríður layer auto-fix; every
    other layer is advisory (flag-only) and leaves the text unchanged.
    """
    selected = set(layers or ())
    fixes = 0

    before = text
    text = normalize_typography(text)
    if text != before:
        fixes += 1

    if greynir:
        sentences = strip_markdown_formatting(text)
        if sentences:
            check_fn = check_with_api if use_api else check_with_library
            results = check_fn(sentences)
            text, n = apply_fixes_to_text(text, results)
            fixes += n

    if "malfridur" in selected:
        try:
            sentences = strip_markdown_formatting(text)
            results = check_with_malfridur(sentences)
            text, n = apply_malfridur_fixes(text, results)
            fixes += n
        except Exception:
            pass

    return text, fixes


def correct_icelandic(
    text: str,
    *,
    mode: str = "full",
    layers: list[str] | None = None,
    threshold: float = 2.0,
    government_path: Path | None = None,
) -> str | list[dict]:
    """High-level entry point.

    - ``mode="full"`` — apply auto-fixes (typography + GreynirCorrect + opt-in
      Málfríður) and return the corrected text.
    - ``mode="greynir-only"`` — apply only GreynirCorrect auto-fixes; return text.
    - ``mode="check"`` — run every layer and return a flat list of issue dicts
      (each tagged with ``layer``); the text is not modified.
    """
    if mode == "check":
        results = run_all_checks(
            text, layers=layers, threshold=threshold, government_path=government_path
        )
        return _flatten_issues(results)
    if mode == "greynir-only":
        corrected, _ = apply_corrections(text, layers=None, greynir=True)
        return corrected
    if mode == "full":
        corrected, _ = apply_corrections(text, layers=layers, greynir=True)
        return corrected
    raise ValueError(f"unknown mode: {mode!r} (expected full|greynir-only|check)")
