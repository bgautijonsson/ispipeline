"""LLM confusable-word pattern scanner.

Merged from the esbvaktin and althingi forks of ``corrections/confusables.py``.

Originally adapted from Þingfréttir (althingi), with significant additions in
ESBvaktin for the EU domain. The biggest ESBvaktin addition is ASCII
transliteration detection — the #1 problem in ESBvaktin's subagent output
(ASCII-ified Icelandic words). The althingi fork meanwhile accumulated
parliamentary-domain confusables (plötusig/plötustig, andstaðan,
weak-superlative u-umlaut, doubled-word detection, etc.).

This module unions ``CONFUSABLE_PATTERNS`` from both forks and de-duplicates the
three entries the forks shared verbatim (bíður upp á, á vikunni, á þessari viku).
Both ``check_confusables`` and ``format_confusable_results`` were byte-identical
across the forks and are preserved as-is.
"""

import re

# Curated deny-list of word pairs/patterns that LLMs commonly confuse.
# Each entry: (regex_pattern, description, suggestion_or_None)
# Extend this list as new error patterns are discovered.
#
# An entry whose description is ``None`` is a *disabled* pattern (kept inline as
# documentation of why it was dropped); the filter below removes such entries.
CONFUSABLE_PATTERNS = [
    # ── ASCII transliteration detection (ESBvaktin's #1 problem) ─────
    # These detect common ASCII-ified Icelandic words in subagent output
    (
        r"\b(?:thjodar|thjodaratkvaed|thjodalif)",
        "ASCII transliteration: 'thjodar...' should use 'þjóðar...' with proper Unicode",
        None,
    ),
    (
        r"\badild(?:ar)?(?:vidraed|samning)",
        "ASCII transliteration: 'adildar...' should use 'aðildar...' with proper Unicode",
        None,
    ),
    (
        r"\bundanth(?:ag|eg)",
        "ASCII transliteration: 'undanth...' should use 'undanþ...' with proper Unicode",
        None,
    ),
    (
        r"\blandbun(?:ad|adar)",
        "ASCII transliteration: 'landbun...' should use 'landbún...' with proper Unicode",
        None,
    ),
    (
        r"\bsjavarutv(?:eg|egs)",
        "ASCII transliteration: 'sjavarutv...' should use 'sjávarútv...' with proper Unicode",
        None,
    ),
    (
        r"\bstadfest(?:a|ir|i)\b",
        "ASCII transliteration: 'stadfest...' should use 'staðfest...' with proper Unicode",
        None,
    ),
    (
        r"\bsamkvaem[td]?\b",
        "ASCII transliteration: 'samkvaem...' should use 'samkvæm...' with proper Unicode",
        None,
    ),
    (
        r"\b(?:ad|af|vid|til)\b(?=\s+[a-z])",
        # Only flag 'ad' when followed by lowercase (to avoid false positives on English 'ad')
        None,  # Too many false positives — skip this one, rely on Unicode paragraph check
        None,
    ),
    (
        r"\btimaaetlun\b",
        "ASCII transliteration: 'timaaetlun' should be 'tímaáætlun'",
        "tímaáætlun",
    ),
    (
        r"\blogsogu\b",
        "ASCII transliteration: 'logsagu' → 'lögsögu' (or 'lögsaga')",
        "lögsögu",
    ),
    (
        r"\bfullyrding(?:ar|ina|una|in)?\b",
        "ASCII transliteration: 'fullyrding...' → 'fullyrðing...'",
        None,
    ),
    # ── Universal confusable patterns (shared across both forks) ────
    # bíða (wait) ≠ bjóða (offer)
    (
        r"\bbíður\s+upp\s+á\b",
        'bíða (wait) ≠ bjóða (offer): "bíður upp á" should be "býður upp á"',
        "býður upp á",
    ),
    # á/í with time expressions
    (
        r"\bá\s+vikunni\b",
        '"á vikunni" — usually should be "í vikunni" (during the week)',
        "í vikunni",
    ),
    (
        r"\bá\s+þessari\s+viku\b",
        '"á þessari viku" — usually should be "í þessari viku"',
        "í þessari viku",
    ),
    # Singular verb + plural subject (ESBvaktin)
    (
        r"\bvar\s+ákvarðanir\b",
        "Singular verb + plural subject: 'var ákvarðanir' → 'voru ákvarðanir'",
        "voru ákvarðanir",
    ),
    # ── Parliamentary-domain confusables (Þingfréttir / althingi) ───
    # grunur = suspicion, not stint/involvement
    (r"\bstuttur\s+grunur\b", "grunur = suspicion, not stint/involvement", None),
    # plötusig vs plötustig confusion (often introduced by auto-fix)
    (
        r"\bplötusig\b",
        "plötusig = record defeat. Did you mean plötustig (record score)?",
        "plötustig",
    ),
    # Word order after "sem" — verb should precede subject
    (
        r"\bsem\s+[A-ZÁÉÍÓÚÝÞÆÖÐ][a-záéíóúýþæöð]+(?:\s+[A-ZÁÉÍÓÚÝÞÆÖÐ][a-záéíóúýþæöð]+)?\s+tók\b",
        'Word order after "sem": verb usually precedes subject (e.g. "sem tók X" not "sem X tók")',
        None,
    ),
    # vonuðum (hoped) ≠ vöruðum (warned)
    (
        r"\bvonuðum\s+við\b",
        "vonuðum (hoped) ≠ vöruðum (warned): check context",
        "vöruðum við",
    ),
    # "andstaðan" alone — should usually be "stjórnarandstaðan" in parliamentary context
    (
        r"\bandstaðan\b(?!\s*og)",
        '"andstaðan" is ambiguous — usually "stjórnarandstaðan" in parliamentary text',
        "stjórnarandstaðan",
    ),
    # endurtekið (past part.) used where endurtekur (present tense) is needed
    (
        r"\bendurtekið\s+sama\b",
        'endurtekið (past part.) — did you mean "endurtekur sama" (present)?',
        None,
    ),
    # "rispuðu platu" — wrong inflection of the award name
    (
        r"\brispuðu\s+platu",
        '"rispuðu platu" — correct form is "rispaða plata" or "rispaða plötu"',
        "rispaða plata",
    ),
    # Repeated adjacent word (typo)
    (
        r"\b(\w{3,})\s+\1\b",
        "Repeated word (likely typo): doubled adjacent word",
        None,
    ),
    # Weak-superlative u-umlaut: 'skarpastu' → 'skörpustu' (promoted from
    # session memory 2026-04-23). Weak superlatives with -u ending trigger
    # u-umlaut on the stem vowel (a → ö).
    (
        r"\bskarpastu\b",
        "Weak superlative with u-ending triggers u-umlaut: skarpastu → skörpustu",
        "skörpustu",
    ),
    # ── Register patterns (inappropriate formality) — ESBvaktin ─────
    (
        r"\bhér\s+að\s+ofan\b",
        "Register: 'hér að ofan' is overly formal for assessments — just state the content",
        None,
    ),
    (
        r"\beins\s+og\s+áður\s+segir\b",
        "Self-reference: 'eins og áður segir' — state the content directly instead",
        None,
    ),
    (
        r"\bsem\s+fyrr\s+greinir\b",
        "Self-reference: 'sem fyrr greinir' — state the content directly instead",
        None,
    ),
    # ── EU terminology patterns — ESBvaktin ─────────────────────────
    (
        r"[Hh]águ.?kjörgæð",
        "Wrong translation: 'Hágu-kjörgæðin' is a hallucination — correct term is 'Haag-viðmiðin' (Hague Preferences)",
        "Haag-viðmiðin",
    ),
    (
        r"\bCommon\s+(?:Agricultural|Fisheries)\s+Policy\b",
        "English EU term in Icelandic text: use 'sameiginleg landbúnaðar/sjávarútvegsstefna'",
        None,
    ),
    (
        r"\bSingle\s+[Mm]arket\b",
        "English EU term in Icelandic text: use 'innri markaðurinn'",
        "innri markaðurinn",
    ),
    (
        r"\bEuropean\s+(?:Commission|Parliament|Council)\b",
        "English EU term in Icelandic text: use Icelandic equivalent",
        None,
    ),
    (
        r"\binngöngu(?:samning|viðræð)",
        "Terminology: 'inngöngu-' → 'aðildar-' for EU accession context",
        None,
    ),
]

# Filter out entries where description is None (disabled patterns)
CONFUSABLE_PATTERNS = [(p, d, s) for p, d, s in CONFUSABLE_PATTERNS if d is not None]


def check_confusables(text: str) -> list[dict]:
    """Scan text for known LLM confusable-word patterns.

    Returns a list of warnings. These are NOT auto-fixed — they require
    human review because context determines correctness.
    """
    warnings = []
    lines = text.split("\n")
    for line_num, line in enumerate(lines, 1):
        for pattern, description, suggestion in CONFUSABLE_PATTERNS:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                warnings.append(
                    {
                        "line": line_num,
                        "match": match.group(),
                        "description": description,
                        "suggestion": suggestion,
                        "context": line.strip()[:100],
                    }
                )
    return warnings


def format_confusable_results(warnings: list[dict], filename: str) -> int:
    """Print confusable-word warnings. Returns count of warnings."""
    if not warnings:
        print(f"  {filename}: No confusable-word patterns found")
        return 0

    for w in warnings:
        print(f'  L{w["line"]:3d} [CONFUSABLE] "{w["match"]}"')
        print(f"        {w['description']}")
        if w["suggestion"]:
            print(f"        → {w['suggestion']}")

    return len(warnings)
