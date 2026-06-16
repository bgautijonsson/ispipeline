"""Register and compound-length checks for Icelandic formal text.

Two advisory checks (flag-only, no auto-correction):

1. Register blocklist — flags English borrowings inappropriate in formal
   parliamentary register and suggests native Icelandic alternatives.

2. Compound-length heuristic — flags words exceeding a character threshold,
   which are often forced neologisms or over-compounded constructions.
"""

import re

# (borrowing, suggested_alternatives)
REGISTER_BLOCKLIST = [
    ("póint", "aðalatriði / kjarni / meginatriði"),
    ("okei", "í lagi / vel"),
    ("djók", "brandari / grín"),
    ("kepp", "lok / úrslit"),
    ("partý", "veisla / samkoma"),
    ("sjansen", "líkur / tækifæri"),
    ("stressað", "álagi / þrýstingi"),
    ("kansen", "tækifæri / líkur"),
    ("basic", "grundvallar- / einfaldur"),
    ("fokus", "áhersla / brennipunktur"),
]

# Pre-compile patterns for performance
_REGISTER_PATTERNS = [
    (re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE), word, suggestion)
    for word, suggestion in REGISTER_BLOCKLIST
]


def check_register(text: str) -> list[dict]:
    """Scan text for English borrowings inappropriate at formal register.

    Returns a list of advisory warnings. These are NOT auto-fixed — they
    require human review because some borrowings may be intentional (e.g.
    in direct quotations).
    """
    results = []
    lines = text.split("\n")
    for line_num, line in enumerate(lines, 1):
        for pattern, word, suggestion in _REGISTER_PATTERNS:
            for match in pattern.finditer(line):
                # Build ~60-char context window around match
                start = max(0, match.start() - 30)
                end = min(len(line), match.end() + 30)
                context = line[start:end].strip()
                if start > 0:
                    context = "..." + context
                if end < len(line):
                    context = context + "..."

                results.append(
                    {
                        "line": line_num,
                        "word": match.group(),
                        "suggestion": suggestion,
                        "context": context,
                    }
                )
    return results


def format_register_results(results: list[dict], filename: str) -> int:
    """Print register-check results. Returns count of flagged borrowings."""
    if not results:
        print(f"  {filename}: No informal borrowings found")
        return 0

    for r in results:
        print(f'  L{r["line"]:3d} [REGISTER] "{r["word"]}"')
        print(f"        → {r['suggestion']}")
        print(f'        "{r["context"]}"')

    return len(results)


def check_compound_length(
    text: str,
    max_chars: int = 25,
) -> list[dict]:
    """Flag words exceeding a character-length threshold.

    Most legitimate Icelandic compounds are under 25 characters. Words
    exceeding this are often forced neologisms or over-compounded
    constructions that should be reviewed for readability.

    Returns a list of advisory warnings (no auto-correction).
    """
    results = []
    lines = text.split("\n")
    for line_num, line in enumerate(lines, 1):
        # Split on whitespace and strip punctuation for length check
        for token in line.split():
            # Strip common trailing/leading punctuation for measurement
            word = token.strip('.,;:!?"\'()[]{}—–-«»„“”')
            if len(word) > max_chars and word.isalpha():
                results.append(
                    {
                        "line": line_num,
                        "word": word,
                        "length": len(word),
                        "reason": (
                            f"Word is {len(word)} characters (>{max_chars}). "
                            "Review for readability — consider splitting or "
                            "rephrasing."
                        ),
                    }
                )
    return results


def format_compound_results(results: list[dict], filename: str) -> int:
    """Print compound-length results. Returns count of flagged words."""
    if not results:
        print(f"  {filename}: No over-long compounds found")
        return 0

    for r in results:
        print(f'  L{r["line"]:3d} [COMPOUND] "{r["word"]}" ({r["length"]} chars)')
        print(f"        {r['reason']}")

    return len(results)
