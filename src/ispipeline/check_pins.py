"""Pin-drift guard — assert every consumer pins the SAME ispipeline git ref.

The whole point of a shared package is that both products run the *same* code. If
esbvaktin and althingi drift onto different ``@vX.Y.Z`` refs, the package has
silently re-forked and the single-source guarantee is gone. This check catches
that. Run it by hand, or from the nightly estate health-monitor workflow (which
has every repo on disk):

    ispipeline-check-pins                          # check the known estate consumers
    ispipeline-check-pins path/to/pyproject.toml … # check explicit pyprojects

Exit code 0 = all consumers pin one ref; 1 = drift (different refs, or a consumer
missing the pin entirely). Pure stdlib — no third-party deps.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Consumers express the pin in one of two equivalent ways; accept both.
# 1. PEP 508 direct reference (esbvaktin):
#       "ispipeline @ git+https://github.com/bgautijonsson/ispipeline.git@v0.1.0"
PIN_PEP508 = re.compile(r"""ispipeline\s*@\s*git\+\S*?@(?P<ref>[^\s"'#,\]]+)""")
# 2. uv [tool.uv.sources] table (althingi):
#       ispipeline = { git = "…", tag = "v0.1.0" }   (or rev = / branch = )
PIN_UV_SOURCE = re.compile(
    r"""ispipeline\s*=\s*\{[^}]*?\b(?:tag|rev|branch)\s*=\s*["'](?P<ref>[^"']+)["']"""
)

# Known estate consumers (overridable on the command line). Each value is the
# pyproject.toml that carries the runtime pin.
DEFAULT_CONSUMERS: dict[str, str] = {
    "esbvaktin": "~/esbvaktin/pyproject.toml",
    "althingi": "~/althingi/althingi-content/pyproject.toml",
}


def find_pin(pyproject_text: str) -> str | None:
    """Return the pinned ispipeline ref found in a pyproject's text, or None.

    Understands both the PEP 508 direct-reference form and uv's
    ``[tool.uv.sources]`` table form, so the two consumers — which happen to use
    different conventions — are compared on the ref, not the syntax.
    """
    for pattern in (PIN_PEP508, PIN_UV_SOURCE):
        match = pattern.search(pyproject_text)
        if match:
            return match.group("ref")
    return None


def check_pins(consumers: dict[str, str]) -> tuple[int, dict[str, str | None]]:
    """Resolve each consumer's pinned ref. Return (exit_code, {name: ref|None})."""
    pins: dict[str, str | None] = {}
    for name, raw_path in consumers.items():
        path = Path(raw_path).expanduser()
        if not path.exists():
            pins[name] = None
            print(f"  {name:<12} pyproject not found — {raw_path}")
            continue
        ref = find_pin(path.read_text(encoding="utf-8"))
        pins[name] = ref
        print(f"  {name:<12} {ref or 'NO ispipeline PIN'}   ({raw_path})")

    missing = [name for name, ref in pins.items() if not ref]
    refs = {ref for ref in pins.values() if ref}

    if missing:
        print(f"DRIFT: {len(missing)} consumer(s) missing the ispipeline pin: {', '.join(missing)}")
        return 1, pins
    if len(refs) > 1:
        print(f"DRIFT: consumers pin DIFFERENT ispipeline refs: {sorted(refs)}")
        return 1, pins
    print(f"OK: all {len(pins)} consumer(s) pin ispipeline@{next(iter(refs))}")
    return 0, pins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispipeline-check-pins",
        description="Assert every consumer pins the same ispipeline git ref (no silent re-fork).",
    )
    parser.add_argument(
        "pyprojects",
        nargs="*",
        help="explicit pyproject.toml paths to check (default: the known estate consumers)",
    )
    args = parser.parse_args(argv)

    if args.pyprojects:
        consumers = {Path(p).expanduser().parent.name or p: p for p in args.pyprojects}
    else:
        consumers = DEFAULT_CONSUMERS

    exit_code, _ = check_pins(consumers)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
