"""ispipeline — shared Icelandic text-correction pipeline for the Metill estate.

This package consolidates the previously-forked ``corrections/`` trees of
esbvaktin (civic / EU register) and althingi (parliamentary register) into a
single, eval-gated library. Consumers pin it by git ref (the iseval pattern)
and enable only the domain layers they need:

    from ispipeline import correct_icelandic
    correct_icelandic(text, mode="full", layers=["eu_terms"])    # civic register
    correct_icelandic(text, mode="full", layers=["ministers"])   # parliamentary register

Every layer degrades gracefully when the optional ``icelandic`` extra
(GreynirCorrect / Icegrams / BÍN) is absent. The high-level entry points live in
``ispipeline.pipeline``; the individual layer functions are re-exported here so a
consumer can do ``from ispipeline import <fn>`` as a near-drop-in replacement for
its old ``from <repo>.corrections import <fn>``.
"""

from __future__ import annotations

__version__ = "0.1.0"

from ispipeline.confusables import (
    CONFUSABLE_PATTERNS,
    check_confusables,
    format_confusable_results,
)
from ispipeline.eu_terms import check_eu_terms, format_eu_term_results
from ispipeline.greynir import (
    AUTO_FIX_CODES,
    PHRASE_FIX_CODES,
    apply_fixes,
    apply_fixes_to_text,
    check_with_api,
    check_with_library,
    format_results,
)
from ispipeline.inflections import (
    _HAS_ISLENSKA,
    _extract_words,
    check_inflections,
    format_inflection_results,
)
from ispipeline.malfridur import (
    apply_malfridur_fixes,
    apply_malfridur_fixes_to_file,
    check_with_malfridur,
    format_malfridur_results,
)
from ispipeline.ministers import check_minister_references, format_minister_results
from ispipeline.naturalness import (
    _HAS_ICEGRAMS,
    check_hedging,
    check_missing_icelandic_chars,
    check_monotonous_openings,
    check_overformal_register,
    format_heuristic_results,
    format_naturalness_results,
    run_heuristic_checks,
    score_naturalness,
)
from ispipeline.parsing import _HAS_GREYNIR, deep_parse, format_deep_parse_results
from ispipeline.pipeline import (
    DOMAIN_LAYERS,
    apply_corrections,
    build_inputs,
    correct_icelandic,
    run_all_checks,
)
from ispipeline.preprocessing import (
    count_typography_issues,
    fix_typography_in_file,
    fix_typography_in_tweets_file,
    normalize_typography,
    strip_direct_quotes_keep_lines,
    strip_markdown_formatting,
    tweets_json_to_text,
)
from ispipeline.register import (
    REGISTER_BLOCKLIST,
    check_compound_length,
    check_register,
    format_compound_results,
    format_register_results,
)

__all__ = [
    "__version__",
    # high-level
    "correct_icelandic",
    "run_all_checks",
    "apply_corrections",
    "build_inputs",
    "DOMAIN_LAYERS",
    # greynir
    "check_with_library",
    "check_with_api",
    "apply_fixes",
    "apply_fixes_to_text",
    "format_results",
    "AUTO_FIX_CODES",
    "PHRASE_FIX_CODES",
    # confusables
    "check_confusables",
    "format_confusable_results",
    "CONFUSABLE_PATTERNS",
    # inflections
    "check_inflections",
    "format_inflection_results",
    "_extract_words",
    "_HAS_ISLENSKA",
    # naturalness
    "score_naturalness",
    "run_heuristic_checks",
    "check_hedging",
    "check_missing_icelandic_chars",
    "check_monotonous_openings",
    "check_overformal_register",
    "format_naturalness_results",
    "format_heuristic_results",
    "_HAS_ICEGRAMS",
    # parsing
    "deep_parse",
    "format_deep_parse_results",
    "_HAS_GREYNIR",
    # preprocessing
    "strip_markdown_formatting",
    "strip_direct_quotes_keep_lines",
    "normalize_typography",
    "count_typography_issues",
    "fix_typography_in_file",
    "fix_typography_in_tweets_file",
    "tweets_json_to_text",
    # domain: civic
    "check_eu_terms",
    "format_eu_term_results",
    "check_with_malfridur",
    "apply_malfridur_fixes",
    "apply_malfridur_fixes_to_file",
    "format_malfridur_results",
    # domain: parliamentary
    "check_minister_references",
    "format_minister_results",
    "check_register",
    "check_compound_length",
    "format_register_results",
    "format_compound_results",
    "REGISTER_BLOCKLIST",
]
