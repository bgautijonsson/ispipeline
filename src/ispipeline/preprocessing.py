"""Text preprocessing: markdown stripping and tweets JSON conversion."""

import json
import re
from pathlib import Path

try:
    from tokenizer import split_into_sentences as _split_sentences

    _HAS_TOKENIZER = True
except ImportError:
    _HAS_TOKENIZER = False


# Icelandic typographic conventions: opening quote is „ (U+201E, low),
# closing quote is " (U+201D, high). LLM-generated narratives occasionally
# emit a straight ASCII " (U+0022) as the closer, which is wrong typography
# and additionally hides the surrounding text from grammar checks (the
# direct-quote stripper treats malformed sequences as protected blocks).
# Restricted to a single line — an unclosed „ should not eat an unrelated
# quote from a later paragraph. Closer can be straight ASCII (") or the
# wrong-direction curly left quote (" U+201C); both get corrected to " U+201D.
_QUOTE_NORMALIZE_RE = re.compile(r"„([^„”\n]*?)[\"“]")


def normalize_typography(text: str) -> str:
    """Normalize Icelandic typography that LLM generation gets wrong.

    Currently handles: straight ASCII closing quote (") after an Icelandic
    opening quote („) → curly closing quote (").

    Pure transformation. Returns the corrected text. Safe to call multiple
    times — idempotent.
    """
    return _QUOTE_NORMALIZE_RE.sub("„\\1”", text)


def count_typography_issues(text: str) -> int:
    """Count typographic issues without changing the text."""
    return sum(1 for _ in _QUOTE_NORMALIZE_RE.finditer(text))


def fix_typography_in_file(filepath: Path) -> int:
    """Apply typographic normalization to a markdown file in-place.

    Returns the number of fixes applied. No write if nothing changed.
    """
    content = filepath.read_text(encoding="utf-8")
    fixes = count_typography_issues(content)
    if fixes == 0:
        return 0
    filepath.write_text(normalize_typography(content), encoding="utf-8")
    return fixes


def fix_typography_in_tweets_file(filepath: Path) -> int:
    """Apply typographic normalization to every text field in a tweets.json.

    Walks the document and rewrites any string under a 'text' key. Returns
    total fixes applied across all tweets. No write if nothing changed.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_fixes = [0]

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "text" and isinstance(v, str):
                    fixes = count_typography_issues(v)
                    if fixes:
                        node[k] = normalize_typography(v)
                        total_fixes[0] += fixes
                else:
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    if total_fixes[0] == 0:
        return 0
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return total_fixes[0]


def _strip_direct_quotes(text: str) -> str:
    """Remove direct MP quotes from text to protect them from correction.

    Strips text enclosed in „..." (Icelandic quotation marks) and «...»
    (alternative quotation marks). These are verbatim parliamentary speech
    and must never be grammar-checked or auto-corrected.
    """
    # „..." — Icelandic quotation marks. Opening is always „ (U+201E).
    # Closing varies: " (U+201C), " (ASCII U+0022), or " (U+201D).
    # Match „ followed by non-quote chars, closed by any of the three.
    text = re.sub("„[^„“”\"]*[“”\"]", "", text)
    # «...» — angle quotation marks
    text = re.sub(r"«[^»]*»", "", text)
    return text


def strip_direct_quotes_keep_lines(text: str) -> str:
    """Strip direct MP quotes while preserving the line count.

    Like :func:`_strip_direct_quotes`, but replaces each removed „..." / «...»
    span with as many newlines as it contained. The flag-only layers
    (confusables, ministers, register, compounds) report line numbers via
    ``text.split("\\n")``, so the substitution must keep newlines intact even
    when a verbatim quote spans multiple lines — otherwise every L### below a
    multi-line quote would be off by one.
    """

    def _repl(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    text = re.sub("„[^„“”\"]*[“”\"]", _repl, text)
    text = re.sub(r"«[^»]*»", _repl, text)
    return text


def strip_markdown_formatting(
    text: str, *, protect_quotes: bool = True
) -> list[tuple[str, int]]:
    """Extract plain-text sentences from markdown, tracking line numbers.

    Skips code blocks, YAML frontmatter, headings (##), table headers (|---|),
    and markdown formatting characters. Returns (sentence, line_number) pairs.

    When *protect_quotes* is True (default), direct MP quotes inside „..."
    and «...» are stripped before sentence splitting so that no downstream
    correction layer ever sees verbatim parliamentary speech.

    When the ``tokenizer`` package is available, uses its Icelandic-aware
    sentence splitter (handles abbreviations like *hv.*, *þm.*, *skv.* and
    numbers correctly). Falls back to one-entry-per-line when unavailable.
    """
    lines = text.split("\n")
    cleaned_lines: list[tuple[str, int]] = []
    in_code_block = False
    in_frontmatter = False

    # Phase 1: strip markdown, collect cleaned lines
    for i, line in enumerate(lines, 1):
        # Skip YAML frontmatter
        if i == 1 and line.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            continue

        # Skip code blocks
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip headings, table separators, empty lines
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or re.match(r"^\|[-\s|]+\|$", stripped)
        ):
            continue

        # Strip markdown formatting but keep the text
        clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)  # images
        clean = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", clean)  # links
        clean = re.sub(r"[*_]{1,3}", "", clean)  # bold/italic
        clean = re.sub(r"^\s*[-*]\s+", "", clean)  # list markers
        clean = re.sub(r"^\s*\d+\.\s+", "", clean)  # numbered lists
        clean = re.sub(r"\|", " ", clean)  # table pipes
        clean = clean.strip()

        # Strip direct MP quotes before further processing
        if protect_quotes:
            clean = _strip_direct_quotes(clean)
            clean = clean.strip()

        if clean and len(clean) > 2:
            cleaned_lines.append((clean, i))

    # Phase 2: split each line into sentences
    sentences: list[tuple[str, int]] = []
    if _HAS_TOKENIZER:
        for line_text, line_num in cleaned_lines:
            for sent in _split_sentences(line_text):
                s = sent.strip()
                if s and len(s) > 2:
                    sentences.append((s, line_num))
    else:
        sentences = cleaned_lines

    return sentences


def tweets_json_to_text(filepath: Path) -> str:
    """Convert a tweets.json file to plain text for grammar checking.

    Returns a markdown-like string with each tweet as a numbered paragraph,
    suitable for processing by strip_markdown_formatting().
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both daily format {"tweets": [...]} and weekly format {"thread": [...], "quotes": [...]}
    tweets = data.get("tweets", [])
    thread = data.get("thread", [])
    quotes = data.get("quotes", [])

    lines = []
    for i, tweet in enumerate(tweets or thread, 1):
        text = tweet.get("text", "")
        if text:
            lines.append(f"Tíst {i}: {text}")
            lines.append("")

    for i, quote in enumerate(quotes, 1):
        text = quote.get("text", "")
        if text:
            lines.append(f"Tilvitnun {i}: {text}")
            lines.append("")

    return "\n".join(lines)
