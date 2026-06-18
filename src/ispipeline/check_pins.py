"""Pin-drift guard — assert every consumer pins the SAME git ref for each shared
estate package (ispipeline, isretrieval, …).

The whole point of a shared package is that every product runs the *same* code.
If two consumers drift onto different ``@vX.Y.Z`` refs, the package has silently
re-forked and the single-source guarantee is gone. This check catches that, for
every estate shared package, across each package's own (different) set of
consumers. Run it by hand, or from the nightly estate health-monitor workflow
(which has every repo on disk):

    ispipeline-check-pins                 # check every known package across its consumers
    ispipeline-check-pins --package isretrieval
    ispipeline-check-pins path/to/pyproject.toml …   # explicit files (use --package)

Exit code 0 = no drift anywhere; 1 = some package has consumers on different refs
(or a consumer missing the pin). Pure stdlib — no third-party deps.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Each shared package and the pyproject.toml of every repo that consumes it.
# (Consumers differ per package — isretrieval reaches frettasafn + althingi-mcp;
# ispipeline reaches althingi-content.) Overridable on the command line.
PACKAGE_CONSUMERS: dict[str, dict[str, str]] = {
    "ispipeline": {
        "esbvaktin": "~/esbvaktin/pyproject.toml",
        "althingi": "~/althingi/althingi-content/pyproject.toml",
    },
    "isretrieval": {
        "esbvaktin": "~/esbvaktin/pyproject.toml",
        "althingi-mcp": "~/althingi/althingi-mcp/pyproject.toml",
        "frettasafn": "~/frettasafn/pyproject.toml",
    },
}


def _patterns(package: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build the two accepted pin syntaxes for a given package name."""
    pkg = re.escape(package)
    # 1. PEP 508 direct reference:  "<pkg> @ git+https://….git@v0.1.0"
    pep508 = re.compile(rf"""(?<![\w-]){pkg}\s*@\s*git\+\S*?@(?P<ref>[^\s"'#,\]]+)""")
    # 2. uv [tool.uv.sources] table:  <pkg> = { git = "…", tag = "v0.1.0" }
    uv_source = re.compile(
        rf"""(?m)^\s*{pkg}\s*=\s*\{{[^}}]*?\b(?:tag|rev|branch)\s*=\s*["'](?P<ref>[^"']+)["']"""
    )
    return pep508, uv_source


def find_pin(pyproject_text: str, package: str = "ispipeline") -> str | None:
    """Return the pinned ref for ``package`` in a pyproject's text, or None.

    Understands both the PEP 508 direct-reference form and uv's
    ``[tool.uv.sources]`` table form, so consumers using different conventions
    are compared on the ref, not the syntax.
    """
    for pattern in _patterns(package):
        match = pattern.search(pyproject_text)
        if match:
            return match.group("ref")
    return None


def check_pins(
    consumers: dict[str, str], package: str = "ispipeline"
) -> tuple[int, dict[str, str | None]]:
    """Resolve each consumer's pinned ref for ``package``. Return (exit_code, pins)."""
    pins: dict[str, str | None] = {}
    for name, raw_path in consumers.items():
        path = Path(raw_path).expanduser()
        if not path.exists():
            pins[name] = None
            print(f"  {name:<14} pyproject not found — {raw_path}")
            continue
        ref = find_pin(path.read_text(encoding="utf-8"), package)
        pins[name] = ref
        print(f"  {name:<14} {ref or f'NO {package} PIN'}   ({raw_path})")

    missing = [name for name, ref in pins.items() if not ref]
    refs = {ref for ref in pins.values() if ref}

    if missing:
        print(f"  DRIFT: {len(missing)} consumer(s) missing the {package} pin: {', '.join(missing)}")
        return 1, pins
    if len(refs) > 1:
        print(f"  DRIFT: consumers pin DIFFERENT {package} refs: {sorted(refs)}")
        return 1, pins
    print(f"  OK: all {len(pins)} consumer(s) pin {package}@{next(iter(refs))}")
    return 0, pins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispipeline-check-pins",
        description="Assert every consumer pins the same git ref for each shared estate package.",
    )
    parser.add_argument(
        "pyprojects",
        nargs="*",
        help="explicit pyproject.toml paths to check (default: every known package + consumer)",
    )
    parser.add_argument(
        "--package",
        choices=sorted(PACKAGE_CONSUMERS),
        help="restrict to one package (default: all known packages)",
    )
    args = parser.parse_args(argv)

    if args.pyprojects:
        package = args.package or "ispipeline"
        consumers = {Path(p).expanduser().parent.name or p: p for p in args.pyprojects}
        return check_pins(consumers, package)[0]

    packages = [args.package] if args.package else list(PACKAGE_CONSUMERS)
    overall = 0
    for package in packages:
        print(f"# {package}")
        code, _ = check_pins(PACKAGE_CONSUMERS[package], package)
        overall = max(overall, code)
        print()
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
