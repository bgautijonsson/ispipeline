"""GreynirCorrect grammar and spelling checks.

Shared by the Metill estate (esbvaktin civic register + althingi parliamentary
register). Merged from the two previously-forked ``corrections/greynir.py``
trees. Unions every guard either fork evolved:

- SIGALRM hang-guard around ``check_single`` (esbvaktin) — legal/regulatory
  text can make GreynirCorrect hang.
- Graceful ``ImportError`` degradation for ``reynir_correct`` (esbvaktin) —
  returns ``[]`` instead of ``sys.exit(1)`` so the rest of the pipeline runs.
- In-quote guard (althingi) — never "correct" verbatim text inside ``„…"`` or
  ``«…»`` direct quotes (MP speech / quoted sources must stay byte-faithful).
- Word-boundary-aware replacement (althingi) — ``\b`` guards so a fix on
  ``þingið`` does not corrupt the compound ``Formannsþingið``.
- BÍN dual-lemma safety gate (both) — skip an S004 "fix" when old and new are
  both valid BÍN words with different lemmas (e.g. plötustig→plötusig).
- S004_SUPPRESS hard-suppress list (both, unioned) — known valid compounds
  GreynirCorrect consistently misidentifies.
- ``apply_fixes_to_text`` for in-memory string correction (esbvaktin) —
  pipeline correction without a file round-trip.

Public surface (consumers import these by name):
    AUTO_FIX_CODES, PHRASE_FIX_CODES, S004_SUPPRESS
    check_with_library, check_with_api
    apply_fixes, apply_fixes_to_text, format_results
    _is_inside_quote   (exercised directly by althingi's test-suite)
"""

import re
import shutil
import signal
import sys
from pathlib import Path

try:
    from islenska import Bin

    _HAS_ISLENSKA = True
except ImportError:
    _HAS_ISLENSKA = False

# Annotation codes that are safe to auto-apply
# S004 = spelling correction, S001 = compound word
AUTO_FIX_CODES = {"S004", "S001"}

# Codes that are phrase-level corrections (high confidence)
PHRASE_FIX_CODES = {"P_afað"}

# S004 words to never "correct" — valid compounds that GreynirCorrect
# misidentifies. UNION of both forks' suppress lists:
#   - esbvaktin: EU-specific terms (aðildarviðræður, sjávarútvegsstefna, …)
#   - althingi:  parliamentary terms (þinglífi, ræðusnild)
# See also: plötustig (caught by the BÍN dual-lemma gate below).
S004_SUPPRESS = {
    # esbvaktin (EU / civic register)
    "aðildarviðræður",
    "sjávarútvegsstefna",
    "landbúnaðarstefna",
    "aðlögunartímabil",
    "viðræðukaflar",
    "sáttmálabókun",
    "kvótakerfi",
    "byggðasjóðir",
    "regluverkið",
    "nálægðarreglan",
    "atkvæðagreiðsla",
    # althingi (parliamentary register)
    "þinglífi",
    "ræðusnild",
}


_reynir_available: bool | None = None


def check_with_library(sentences: list[tuple[str, int]]) -> list[dict]:
    """Check sentences using local GreynirCorrect library.

    Degrades gracefully (returns ``[]``) when ``reynir-correct`` is not
    installed, and guards each ``check_single`` call with a 10s SIGALRM
    timeout — complex legal/regulatory text can make it hang.
    """
    global _reynir_available
    if _reynir_available is False:
        return []
    try:
        from reynir_correct import check_single

        _reynir_available = True
    except ImportError:
        _reynir_available = False
        print(
            "WARNING: reynir-correct not installed. Run: uv pip install reynir-correct",
            file=sys.stderr,
        )
        return []

    results = []
    for text, line_num in sentences:
        # Timeout guard: check_single can hang on complex legal/regulatory text
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"check_single timed out on: {text[:80]}...")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(10)
        try:
            sent = check_single(text)
        except TimeoutError as e:
            print(f"WARNING: {e} — skipping", file=sys.stderr)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            continue
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        for ann in sent.annotations:
            results.append(
                {
                    "line": line_num,
                    "code": ann.code,
                    "text": ann.text,
                    "detail": ann.detail or "",
                    "suggest": ann.suggest or "",
                    "original": text,
                    "corrected": sent.tidy_text,
                    "auto_fixable": ann.code in AUTO_FIX_CODES
                    or ann.code in PHRASE_FIX_CODES,
                }
            )
    return results


def check_with_api(sentences: list[tuple[str, int]]) -> list[dict]:
    """Check sentences using yfirlestur.is REST API."""
    import httpx

    results = []
    # Batch sentences to reduce API calls (max ~50 per request)
    batch_size = 20
    all_sentences = list(sentences)

    for batch_start in range(0, len(all_sentences), batch_size):
        batch = all_sentences[batch_start : batch_start + batch_size]
        text = "\n".join(s[0] for s in batch)

        resp = httpx.post(
            "https://yfirlestur.is/correct.api",
            data={"text": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for i, paragraph in enumerate(data.get("result", [])):
            for sent_data in paragraph:
                line_num = batch[min(i, len(batch) - 1)][1]
                for ann in sent_data.get("annotations", []):
                    results.append(
                        {
                            "line": line_num,
                            "code": ann["code"],
                            "text": ann["text"],
                            "detail": ann.get("detail", ""),
                            "suggest": ann.get("suggest", ""),
                            "original": sent_data.get("original", ""),
                            "corrected": sent_data.get("corrected", ""),
                            "auto_fixable": ann["code"] in AUTO_FIX_CODES
                            or ann["code"] in PHRASE_FIX_CODES,
                        }
                    )

    return results


def _is_inside_quote(content: str, match_start: int) -> bool:
    """Check if a position in the text falls inside a direct quote.

    Protects text inside ``„..."`` and ``«...»`` from being modified —
    these are verbatim quotes (MP speech, cited sources) that must never
    be altered.
    """
    for pattern in ["„[^„“”\"]*[“”\"]", "«[^»]*»"]:
        for m in re.finditer(pattern, content):
            if m.start() <= match_start < m.end():
                return True
    return False


def _apply_fix_to_content(content: str, r: dict) -> tuple[str, bool]:
    """Apply a single fix to a content string. Returns (new_content, was_applied).

    Shared by both ``apply_fixes`` (file-backed) and ``apply_fixes_to_text``
    (in-memory string) so the guard logic lives in exactly one place.

    Guards applied (union of both forks):
      1. Hard suppress list (S004_SUPPRESS) — never touch known valid compounds.
      2. BÍN dual-lemma gate — skip S004 when old/new are both valid BÍN words
         with different lemmas (the "fix" would change meaning).
      3. Word-boundary-aware match (``\\b…\\b``) — Python 3's ``\\w`` is
         Unicode-aware, so ``þingið`` will not match inside ``Formannsþingið``.
      4. In-quote guard — never modify text inside ``„..."`` / ``«...»``.
    """
    if not r["auto_fixable"] or not r["suggest"]:
        return content, False

    code = r["code"]
    if code in AUTO_FIX_CODES:
        # Spelling: extract the misspelled word from the annotation text
        # Format: "Orðið 'X' var leiðrétt í 'Y'"
        m = re.search(r"'([^']+)' var leiðrétt í '([^']+)'", r["text"])
        if m:
            old_word, new_word = m.group(1), m.group(2)
            # Hard suppress list: known valid compounds that
            # GreynirCorrect consistently misidentifies
            if code == "S004" and old_word in S004_SUPPRESS:
                print(
                    f"  [SKIP] S004 '{old_word}'→'{new_word}': "
                    f"suppressed (known valid compound)"
                )
                return content, False
            # Safety gate: if both old and new are valid BÍN words with
            # different lemmas, the "fix" may destroy meaning (e.g.
            # plötustig→plötusig where stig=score vs sig=defeat)
            if _HAS_ISLENSKA and code == "S004":
                b = Bin()
                _, old_meanings = b.lookup(old_word)
                _, new_meanings = b.lookup(new_word)
                if old_meanings and new_meanings:
                    old_lemmas = {m_.ord for m_ in old_meanings}
                    new_lemmas = {m_.ord for m_ in new_meanings}
                    if old_lemmas != new_lemmas:
                        print(
                            f"  [SKIP] S004 '{old_word}'→'{new_word}': "
                            f"both valid BÍN words with different lemmas "
                            f"({old_lemmas} vs {new_lemmas})"
                        )
                        return content, False
            # Replace in content (word-boundary aware, skip quotes).
            # Python 3's \w is Unicode-aware so \b correctly treats
            # Icelandic letters (þ ð æ ö áéíóúý) as word characters —
            # 'þingið' will not match inside 'Formannsþingið'.
            pattern = re.compile(rf"\b{re.escape(old_word)}\b")
            match = pattern.search(content)
            if match:
                if _is_inside_quote(content, match.start()):
                    print(
                        f"  [SKIP] {code} '{old_word}'→'{new_word}': "
                        f"inside direct quote"
                    )
                    return content, False
                content = (
                    content[: match.start()] + new_word + content[match.end() :]
                )
                return content, True

    elif code in PHRASE_FIX_CODES:
        # Phrase corrections: extract old and new phrases
        m = re.search(r"'([^']+)' var leiðrétt í '([^']+)'", r["text"])
        if m:
            old_phrase, new_phrase = m.group(1), m.group(2)
            idx = content.find(old_phrase)
            if idx >= 0:
                if _is_inside_quote(content, idx):
                    print(
                        f"  [SKIP] {code} '{old_phrase}'→'{new_phrase}': "
                        f"inside direct quote"
                    )
                    return content, False
                content = (
                    content[:idx] + new_phrase + content[idx + len(old_phrase) :]
                )
                return content, True

    return content, False


def apply_fixes(filepath: Path, results: list[dict]) -> int:
    """Apply auto-fixable corrections to a file. Returns count of applied fixes.

    Only applies spelling corrections (S004, S001) and high-confidence
    phrase corrections (P_afað). Never modifies text inside direct quotes
    (``„..."`` or ``«...»``). Writes a ``.bak`` sibling before overwriting.
    """
    content = filepath.read_text(encoding="utf-8")
    fixes_applied = 0

    for r in results:
        content, applied = _apply_fix_to_content(content, r)
        if applied:
            fixes_applied += 1

    if fixes_applied > 0:
        shutil.copy2(filepath, filepath.with_suffix(filepath.suffix + ".bak"))
        filepath.write_text(content, encoding="utf-8")

    return fixes_applied


def apply_fixes_to_text(text: str, results: list[dict]) -> tuple[str, int]:
    """Apply auto-fixable corrections to a string. Returns (corrected_text, count).

    In-memory counterpart to ``apply_fixes`` for pipeline use (no file
    round-trip). Same guard logic via the shared ``_apply_fix_to_content``.
    """
    fixes_applied = 0
    for r in results:
        text, applied = _apply_fix_to_content(text, r)
        if applied:
            fixes_applied += 1
    return text, fixes_applied


def format_results(results: list[dict], filename: str) -> tuple[int, int, int]:
    """Print formatted results. Returns (errors, warnings, auto_fixable)."""
    errors = 0
    warnings = 0
    auto_fixable = 0

    if not results:
        print(f"  {filename}: No issues found")
        return 0, 0, 0

    for r in results:
        code = r["code"]
        icon = "FIX" if r["auto_fixable"] else "CHECK"

        if r["auto_fixable"]:
            auto_fixable += 1
        elif code.startswith("P_"):
            errors += 1
        else:
            warnings += 1

        print(f"  L{r['line']:3d} [{icon}] {code}: {r['text']}")
        if r["suggest"]:
            print(f"        → {r['suggest']}")
        if r["detail"] and not r["auto_fixable"]:
            print(f"        ℹ {r['detail']}")

    return errors, warnings, auto_fixable
