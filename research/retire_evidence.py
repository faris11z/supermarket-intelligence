"""Record the deliberate deletion of an evidence file.

Usage:

    python -m research.retire_evidence --list
    python -m research.retire_evidence data/research/raw/... --reason "..."   # dry run
    python -m research.retire_evidence data/research/raw/... --reason "..." --apply

Why this exists as a tool rather than a manual edit. Seven evidence files were
deleted during Phase 3 and the tombstones were typed into the request log by
hand. That works, but it means the log is no longer purely machine-written, and
a reader cannot tell a hand-written tombstone from a generated one. This module
emits the same record shape through the normal append path, which is what makes
"the log is append-only and written by this harness" true rather than aspirational.

The log is the record of what happened. A tombstone is a fact about a *local
file*, not an HTTP request, so the record carries method "DELETE" and an empty
URL rather than pretending to be a request.
"""

from __future__ import annotations

import json
import sys

from . import config
from .models import RequestRecord
from .probes.common import RequestLog


def latest_by_path(log: RequestLog) -> dict[str, RequestRecord]:
    """Latest record per evidence path, mirroring verify_phase3.py."""
    latest: dict[str, RequestRecord] = {}
    for line in log.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = RequestRecord.from_dict(json.loads(line))
        if record.evidence_path:
            latest[record.evidence_path] = record
    return latest


def main(argv: list[str]) -> int:
    config.ensure_dirs()
    args = [a for a in argv[1:] if not a.startswith("-")]
    apply = "--apply" in argv
    reason = ""
    if "--reason" in argv:
        index = argv.index("--reason")
        if index + 1 < len(argv):
            reason = argv[index + 1]

    if not config.REQUEST_LOG.exists():
        print(f"no request log at {config.REQUEST_LOG}", file=sys.stderr)
        return 1

    log = RequestLog()
    latest = latest_by_path(log)

    if not args or "--list" in argv:
        print("evidence paths currently referenced by the request log:")
        for path, record in sorted(latest.items()):
            exists = (config.REPO_ROOT / path).exists()
            state = "on disk" if exists else "MISSING"
            if record.result == "evidence_retired":
                state = "retired by design"
            print(f"  [{state:>16}] {path}")
        print()
        print(
            f"{len(latest)} paths referenced, "
            f"{sum(1 for r in latest.values() if r.result == 'evidence_retired')} retired"
        )
        return 0

    if not reason:
        print("--reason is required: a tombstone without a reason is not evidence",
              file=sys.stderr)
        return 2

    unknown = [p for p in args if p not in latest]
    if unknown:
        print(f"not referenced by the request log: {unknown}", file=sys.stderr)
        return 2

    for path in args:
        if (config.REPO_ROOT / path).exists():
            print(f"refusing: {path} still exists. Delete the file first, then "
                  f"record the tombstone, or the two steps disagree.", file=sys.stderr)
            return 2

    for path in args:
        if apply:
            log.retire(path, reason)
            print(f"recorded tombstone: {path}")
        else:
            print(f"would record tombstone: {path}")
            print(f"  reason: {reason}")
    if not apply:
        print()
        print("dry run. add --apply to append the tombstone to the request log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
