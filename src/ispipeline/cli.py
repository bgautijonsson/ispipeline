"""ispipeline.cli — generic command-line interface over the correction pipeline.

This is deliberately consumer-agnostic: it operates on files or stdin, not on a
project's narrative-file layout. Consumers keep their own thin wrappers (which
know about weekly digests, editorials, etc.) and call into ``ispipeline``.

    ispipeline FILE...                 # check files, print per-layer counts
    ispipeline FILE --fix              # apply typography + GreynirCorrect fixes in place
    ispipeline FILE --layers eu_terms  # also run an opt-in domain layer
    cat note.md | ispipeline           # check stdin

Exit codes: 1 if any layer flagged something, 0 if clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ispipeline.pipeline import DOMAIN_LAYERS, apply_corrections, run_all_checks


def _count(results: dict) -> int:
    total = 0
    for value in results.values():
        if isinstance(value, dict):
            total += sum(len(items) for items in value.values())
        else:
            total += len(value)
    return total


def _emit_text(results: dict, name: str) -> int:
    print(f"=== {name} ===")
    total = 0
    for layer, value in results.items():
        count = sum(len(i) for i in value.values()) if isinstance(value, dict) else len(value)
        total += count
        if count:
            print(f"  {layer}: {count}")
    print(f"  total: {total}")
    return 1 if total else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispipeline",
        description="Check or auto-correct Icelandic text (Metill shared correction pipeline).",
    )
    parser.add_argument("files", nargs="*", help="files to check (default: read stdin)")
    parser.add_argument(
        "--fix", action="store_true", help="apply typography + GreynirCorrect fixes in place"
    )
    parser.add_argument(
        "--layers",
        default="",
        help=f"comma-separated opt-in domain layers ({', '.join(DOMAIN_LAYERS)})",
    )
    parser.add_argument(
        "--threshold", type=float, default=2.0, help="naturalness threshold in sigma (default 2.0)"
    )
    parser.add_argument(
        "--government-json", help="path to government.json for the `ministers` layer"
    )
    parser.add_argument("--json", action="store_true", help="emit results as JSON")
    args = parser.parse_args(argv)

    layers = [layer for layer in args.layers.split(",") if layer]
    gov = Path(args.government_json) if args.government_json else None

    if not args.files:
        text = sys.stdin.read()
        if args.fix:
            corrected, n = apply_corrections(text, layers=layers)
            sys.stdout.write(corrected)
            print(f"[ispipeline] {n} fix(es) applied", file=sys.stderr)
            return 0
        results = run_all_checks(
            text, layers=layers, threshold=args.threshold, government_path=gov
        )
        if args.json:
            json.dump({"<stdin>": results}, sys.stdout, ensure_ascii=False, indent=2, default=list)
            print()
            return 1 if _count(results) else 0
        return _emit_text(results, "<stdin>")

    exit_code = 0
    all_results: dict[str, dict] = {}
    for filename in args.files:
        path = Path(filename)
        if not path.exists():
            print(f"  {filename}: SKIPPED (not found)", file=sys.stderr)
            continue
        if args.fix:
            corrected, n = apply_corrections(path.read_text(encoding="utf-8"), layers=layers)
            path.write_text(corrected, encoding="utf-8")
            print(f"  {filename}: {n} fix(es) applied")
            continue
        results = run_all_checks(
            path.read_text(encoding="utf-8"),
            layers=layers,
            threshold=args.threshold,
            government_path=gov,
        )
        all_results[filename] = results
        if not args.json:
            exit_code = max(exit_code, _emit_text(results, filename))
        else:
            exit_code = max(exit_code, 1 if _count(results) else 0)

    if args.json and not args.fix:
        json.dump(all_results, sys.stdout, ensure_ascii=False, indent=2, default=list)
        print()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
