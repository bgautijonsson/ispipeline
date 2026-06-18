"""Nightly estate-health runner — wraps the on-demand monitor for unattended use.

Runs the same checks as ``ispipeline-estate-health``, then:

  * appends the full report to an Obsidian log note (**always** — a quiet record);
  * fires a macOS notification **only** on a FAIL, or when a source becomes
    *newly* stale (flagged ``[STALE]`` now but not on the previous run).

The second rule is the point: the estate carries chronic advocacy-feed staleness
(parties that simply don't post often), so alerting on every WARN would nag
nightly. A *new* staleness — e.g. a mainline news feed breaking — is the signal
worth a push. Pure stdlib + :mod:`ispipeline.estate_health`.

Scheduled via launchd (``is.metill.estate-health``, nightly ~08:00). On demand::

    ispipeline-estate-health-nightly                 # run + log + maybe-notify
    ispipeline-estate-health-nightly --no-notify     # run + log only
    ispipeline-estate-health-nightly --log-file PATH --state-file PATH
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ispipeline.estate_health import (
    FAIL,
    render,
    run_pin_guards,
    run_repo_health,
    summarise,
)

# Defaults are personal-estate paths, consistent with estate_health's hardcoded
# REPO_HEALTH roots. Override with --log-file / --state-file for other setups.
DEFAULT_LOG = Path("~/Obsidian/Metill/Estate Health Log.md").expanduser()
DEFAULT_STATE = Path("~/.cache/ispipeline/estate-health.state.json").expanduser()

_STALE_RE = re.compile(r"\[STALE\]\s+(\S+)")


def stale_sources(rows: list[tuple[str, str, str]]) -> set[str]:
    """Source ids flagged ``[STALE]`` anywhere in the report details."""
    found: set[str] = set()
    for _, _, detail in rows:
        found.update(_STALE_RE.findall(detail))
    return found


def load_prior_stale(path: Path) -> set[str] | None:
    """Previous run's stale set, or ``None`` if there is no prior run (so the
    first run records a baseline instead of alerting on everything)."""
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("stale", []))
    except (FileNotFoundError, ValueError, OSError):
        return None


def save_stale(path: Path, stale: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stale": sorted(stale)}, ensure_ascii=False), encoding="utf-8")


def append_log(path: Path, timestamp: str, overall: str, counts: dict[str, int], report: str) -> None:
    """Append a fenced report block to the Obsidian log note (created if absent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    header = (
        f"## {timestamp} — {overall} "
        f"({counts['OK']} OK · {counts['WARN']} WARN · {counts['FAIL']} FAIL)"
    )
    with path.open("a", encoding="utf-8") as fh:
        if new_file:
            fh.write("# Estate Health Log\n\nAutomated nightly `ispipeline-estate-health` runs.\n")
        fh.write(f"\n{header}\n\n```\n{report}\n```\n")


def notify(title: str, message: str) -> None:
    """Best-effort macOS notification; a no-op where ``osascript`` is absent."""
    if not shutil.which("osascript"):
        return
    safe = message.replace('"', "'")
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe}" with title "{title}"'],
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispipeline-estate-health-nightly",
        description="Unattended estate-health run: always log, notify only on FAIL / new staleness.",
    )
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG, help="Obsidian log note")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE, help="stale-set state")
    parser.add_argument("--no-notify", action="store_true", help="never send a notification")
    parser.add_argument("--timeout", type=int, default=120, help="per-repo health-script timeout (s)")
    args = parser.parse_args(argv)

    rows = run_pin_guards() + run_repo_health(args.timeout)
    overall, counts = summarise(rows)
    report = render(rows, quiet=False)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Always record — but never let a logging failure (vault unmounted) kill the run.
    try:
        append_log(args.log_file, timestamp, overall, counts, report)
    except OSError as exc:  # pragma: no cover - filesystem edge
        print(f"[nightly] log append failed: {exc}")

    current = stale_sources(rows)
    prior = load_prior_stale(args.state_file)
    newly_stale = current - prior if prior is not None else set()
    try:
        save_stale(args.state_file, current)
    except OSError as exc:  # pragma: no cover - filesystem edge
        print(f"[nightly] state save failed: {exc}")

    if not args.no_notify:
        if counts[FAIL]:
            notify("Estate health: FAIL", f"{counts[FAIL]} check(s) failed — see the log note")
        elif newly_stale:
            notify("Estate health: new staleness", "Newly stale: " + ", ".join(sorted(newly_stale)))

    print(report)
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
