"""Minister portfolio fact-checking against government.json.

Ported verbatim from the althingi fork (parliamentary layer). esbvaktin has no
counterpart, so there is nothing to union. The module uses only the standard
library (``json``, ``re``, ``pathlib``) — there are no intra-package or
third-party imports to rewrite, and no optional-dependency degradation is
required here.

By default the cabinet data is read from a ``knowledge/government.json`` file
located one directory above this package's source root, preserving the althingi
layout (``corrections/ministers.py`` → ``knowledge/government.json``). Callers
that ship their own cabinet data should pass ``government_path`` explicitly.
"""

import json
import re
from pathlib import Path


def check_minister_references(
    text: str, government_path: Path | None = None
) -> list[dict]:
    """Cross-reference minister portfolio claims against government.json.

    Scans narrative text for minister name mentions followed by role words.
    Flags mismatches between the text and the authoritative cabinet data.
    """
    if government_path is None:
        government_path = Path(__file__).resolve().parent.parent / "knowledge" / "government.json"

    if not government_path.exists():
        return []

    gov_data = json.loads(government_path.read_text(encoding="utf-8"))
    cabinet = gov_data.get("cabinet", [])
    if not cabinet:
        return []

    # Build name → roles mapping
    minister_roles: dict[str, dict] = {}
    for entry in cabinet:
        name = entry["name"]
        minister_roles[name] = {
            "role_is": entry["role_is"],
            "role_en": entry["role_en"],
            "party": entry["party"],
        }
        # Also index by first name + patronymic (e.g. "Þorgerður Katrín")
        parts = name.split()
        if len(parts) >= 2:
            # First name only
            minister_roles.setdefault(
                parts[0],
                {
                    "role_is": entry["role_is"],
                    "role_en": entry["role_en"],
                    "party": entry["party"],
                    "_partial": True,
                },
            )

    warnings = []
    lines = text.split("\n")
    seen: set[tuple[int, str, str]] = set()  # dedupe (line, name, found_role)

    def _compare_and_flag(
        line_num: int,
        name: str,
        info: dict,
        window: str,
        source_line: str,
    ) -> None:
        """Check a 120-char text window for a ráðherra mention; if found and
        it doesn't match the minister's correct role, emit a warning."""
        radh_match = re.search(r"(\w*ráðherra\w*)", window.lower())
        if not radh_match:
            return
        found_role = radh_match.group(1)
        # Normalise: strip Icelandic case suffixes so 'fjármálaráðherrans'
        # matches 'fjármálaráðherra'.
        found_base = re.sub(r"(ráðherra)(?:ns?|num|a|ann)?$", r"\1", found_role)
        role_base = re.sub(
            r"(ráðherra)(?:ns?|num|a|ann)?$",
            r"\1",
            info["role_is"].lower(),
        )
        if found_base == role_base or found_base == "ráðherra":
            return
        key = (line_num, name, found_role)
        if key in seen:
            return
        seen.add(key)
        warnings.append(
            {
                "line": line_num,
                "name": name,
                "found_role": found_role,
                "correct_role": info["role_is"],
                "context": source_line.strip()[:120],
            }
        )

    for line_num, line in enumerate(lines, 1):
        for name, info in minister_roles.items():
            if info.get("_partial"):
                continue  # Only check full names for attribution
            if name not in line:
                continue

            name_pos = line.find(name)
            # Forward scan: role mentioned AFTER the name (", X-ráðherra")
            forward = line[name_pos + len(name) : name_pos + len(name) + 120]
            _compare_and_flag(line_num, name, info, forward, line)
            # Backward scan: role mentioned BEFORE the name ("X-ráðherra Name")
            # Audit finding P1.M2 — genitive-name forms deferred.
            backward = line[max(0, name_pos - 120) : name_pos]
            _compare_and_flag(line_num, name, info, backward, line)

    return warnings


def format_minister_results(warnings: list[dict], filename: str) -> int:
    """Print minister fact-check results. Returns count of warnings."""
    if not warnings:
        print(f"  {filename}: Minister references OK")
        return 0

    for w in warnings:
        print(
            f"  L{w['line']:3d} [MINISTER] {w['name']}: "
            f'found "{w["found_role"]}" but correct role is "{w["correct_role"]}"'
        )
        print(f'        in: "{w["context"]}"')

    return len(warnings)
