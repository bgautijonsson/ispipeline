"""Estate health monitor (on-demand).

Runs two kinds of check and prints one aggregated report:
  1. The pin-drift guard across every shared package (cross-repo — only this
     monitor can see it).
  2. Each repo's own non-interactive health script (frettasafn + althingi each
     have ``scripts/health_report.py``; esbvaktin's health is an interactive
     skill, so it's covered here only by the pin guard + its CI).

    ispipeline-estate-health            # full report
    ispipeline-estate-health --quiet    # only WARN/FAIL sections

Exit 0 if nothing FAILed (pin drift / crash / timeout), 1 otherwise. WARN is
advisory (e.g. a repo's freshness script flagging stale data). Pure stdlib +
ispipeline. No scheduling — wrapping this in a nightly job is a separate, deferred
decision; run it on demand for now.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from ispipeline.check_pins import PACKAGE_CONSUMERS, check_pins


def _subprocess_env() -> dict[str, str]:
    """Child env without VIRTUAL_ENV, so each repo's ``uv run`` targets its own
    .venv silently instead of warning about a mismatch with ispipeline's."""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return env

# Repos exposing a non-interactive health script (cmd run with cwd = repo root).
REPO_HEALTH: list[tuple[str, str, list[str]]] = [
    ("frettasafn", "~/frettasafn", ["uv", "run", "python", "scripts/health_report.py"]),
    ("althingi", "~/althingi", ["uv", "run", "python", "scripts/health_report.py"]),
]

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def run_pin_guards() -> list[tuple[str, str, str]]:
    """Run the pin-drift guard for every shared package. Drift is a FAIL."""
    rows: list[tuple[str, str, str]] = []
    for package, consumers in PACKAGE_CONSUMERS.items():
        buf = io.StringIO()
        with redirect_stdout(buf):
            code, _ = check_pins(consumers, package)
        rows.append((f"pins:{package}", OK if code == 0 else FAIL, buf.getvalue().rstrip()))
    return rows


def run_repo_health(timeout: int = 120) -> list[tuple[str, str, str]]:
    """Run each repo's health script. A non-zero exit is advisory (WARN); a
    crash/timeout/missing-repo is a FAIL only when it means we couldn't check."""
    rows: list[tuple[str, str, str]] = []
    for name, cwd, cmd in REPO_HEALTH:
        path = Path(cwd).expanduser()
        if not path.exists():
            rows.append((f"health:{name}", WARN, f"repo not found: {cwd}"))
            continue
        try:
            proc = subprocess.run(
                cmd, cwd=path, capture_output=True, text=True, timeout=timeout,
                env=_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            rows.append((f"health:{name}", FAIL, f"health check timed out after {timeout}s"))
            continue
        except (FileNotFoundError, OSError) as exc:
            rows.append((f"health:{name}", FAIL, f"could not run health check: {exc}"))
            continue
        detail = (proc.stdout + proc.stderr).rstrip()
        status = OK if proc.returncode == 0 else WARN
        rows.append((f"health:{name}", status, detail))
    return rows


def summarise(rows: list[tuple[str, str, str]]) -> tuple[str, dict[str, int]]:
    """Return (overall_status, counts). FAIL beats WARN beats OK."""
    counts = {OK: 0, WARN: 0, FAIL: 0}
    for _, status, _ in rows:
        counts[status] += 1
    overall = FAIL if counts[FAIL] else WARN if counts[WARN] else OK
    return overall, counts


def render(rows: list[tuple[str, str, str]], *, quiet: bool = False) -> str:
    """Render the aggregated report. In quiet mode, OK rows are omitted."""
    overall, counts = summarise(rows)
    lines = [
        f"Metill estate health: {overall}  "
        f"({counts[OK]} OK · {counts[WARN]} WARN · {counts[FAIL]} FAIL)",
        "",
    ]
    for name, status, detail in rows:
        if quiet and status == OK:
            continue
        lines.append(f"[{status:<4}] {name}")
        if detail:
            lines.extend(f"        {line}" for line in detail.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispipeline-estate-health",
        description="On-demand Metill estate health monitor (pin guard + per-repo health).",
    )
    parser.add_argument("--quiet", action="store_true", help="only show WARN/FAIL sections")
    parser.add_argument(
        "--timeout", type=int, default=120, help="per-repo health-script timeout in seconds"
    )
    args = parser.parse_args(argv)

    rows = run_pin_guards() + run_repo_health(args.timeout)
    print(render(rows, quiet=args.quiet))
    overall, _ = summarise(rows)
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
