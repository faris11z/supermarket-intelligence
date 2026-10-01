"""Entry point for a Phase 3 research run.

Usage:

    python -m research.run_probe              # everything
    python -m research.run_probe aldi         # one source
    python -m research.run_probe lidl lidl    # one source twice is a mistake
    python -m research.run_probe --list       # show source names

Outputs, all under data/research/:

    request_log.jsonl            append-only, one JSON object per request
    reports/<source>.json        full findings per source
    reports/run_summary.json     counts across the run
    normalized/<source>_products.json  the comparable product records

This script performs network requests. It is not a test suite. Running it
twice will make twice as many requests, which is why it appends to the request
log rather than pretending to be idempotent.
"""

from __future__ import annotations

import sys

from . import config
from .http_client import is_offline, polite_sleep, request_count, set_offline
from .models import RequestRecord
from .probes import aldi, alternative_sources, lidl
from .probes.common import RequestLog, write_json

PROBES = {
    "aldi": aldi.run,
    "lidl": lidl.run,
    "alternatives": alternative_sources.run,
}


def main(argv: list[str]) -> int:
    config.ensure_dirs()

    offline = "--offline" in argv
    if offline:
        set_offline(True)

    args = [a for a in argv[1:] if not a.startswith("-")]
    if "--list" in argv:
        print("available sources:")
        for name in PROBES:
            print(f"  {name}")
        return 0

    if not args:
        args = list(PROBES)

    unknown = [a for a in args if a not in PROBES]
    if unknown:
        print(f"unknown source(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"choose from: {', '.join(PROBES)}", file=sys.stderr)
        return 2

    if len(set(args)) != len(args):
        print("refusing to probe the same source twice in one run", file=sys.stderr)
        return 2

    log = RequestLog()
    print(f"Phase 3 run starting at {config.utc_now()}")
    print(f"mode           : {'OFFLINE (replaying saved evidence)' if is_offline() else 'ONLINE'}")
    print(f"request log: {log.path}")
    print(f"sources: {', '.join(args)}")
    print("-" * 70)

    summary: dict[str, object] = {
        "started_utc": config.utc_now(),
        "sources": args,
        "user_agent": config.USER_AGENT,
        "mode": "offline-replay" if is_offline() else "online",
    }

    for name in args:
        print(f"[{name}] probing...")
        try:
            findings = PROBES[name](log)
        except Exception as exc:  # noqa: BLE001 - a probe failure must not abort the run
            findings = {"source": name, "error": f"{type(exc).__name__}: {exc}"}
            print(f"[{name}] FAILED: {type(exc).__name__}: {exc}")

        path = write_json(config.REPORTS_DIR / f"{name}.json", findings)
        print(f"[{name}] wrote {path.relative_to(config.REPO_ROOT)}")

        observations = findings.get("observations") or findings.get("products")
        if isinstance(observations, list) and observations:
            norm = write_json(
                config.NORMALIZED_DIR / f"{name}_products.json", observations
            )
            print(f"[{name}] normalized {len(observations)} records -> {norm.relative_to(config.REPO_ROOT)}")
            summary[f"{name}_record_count"] = len(observations)

        summary[f"{name}_result"] = "ok" if "error" not in findings else "error"
        polite_sleep()

    counts = log.counts()
    summary["finished_utc"] = config.utc_now()
    summary["requests_made"] = request_count()
    summary["results_by_type"] = counts
    if not is_offline():
        summary["blocked_urls"] = [r.url for r in log.blocked()]
    write_json(config.REPORTS_DIR / "run_summary.json", summary)

    print("-" * 70)
    if is_offline():
        print("offline replay: no network requests were made")
    else:
        print(f"requests this run : {request_count()}")
    for key, value in sorted(counts.items()):
        print(f"  {key:12s} : {value}")
    print(f"summary: {(config.REPORTS_DIR / 'run_summary.json').relative_to(config.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
