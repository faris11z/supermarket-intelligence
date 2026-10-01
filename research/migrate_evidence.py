"""Give the legacy evidence files content-addressed names. Dry run by default.

Usage:

    python -m research.migrate_evidence            # show what would change
    python -m research.migrate_evidence --apply    # rename, dedupe, write manifest

What it does. 41 of the 58 current evidence files are named after the URL alone,
because they were fetched before `_safe_name` accepted a content digest. There
are two distinct cases among them:

  * 34 have no content-addressed twin, so they are renamed to
    `<url-stem>-<12 hex of the decoded sha256><suffix>`, the scheme already used
    for evidence fetched after the fix;
  * 7 already have a content-addressed twin that is byte-identical. Those are
    duplicate copies left behind by the re-fetch, and the honest end state is to
    delete them and record a tombstone, not to keep a second copy of the same
    bytes under a second name.

What it deliberately does not do. It does not touch existing lines of
`request_log.jsonl`. The log is the record of what was requested, and rewriting a
pointer inside it would make the one file we promise is append-only into the one
file that is not. New tombstones are appended through `RequestLog.retire`, which
is the normal path. The manifest maps old paths to new ones, and
`verify_phase3.py` resolves through it.

Safety. A rename is refused if the target already exists with different bytes, if
the source is missing, or if the source has no recorded digest to address it by.
The digest recorded in the log is used, never a freshly computed one, so the
manifest cannot quietly disagree with the log.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from typing import Any
from urllib.parse import urlparse

from . import config, evidence_manifest
from .http_client import _safe_name
from .models import RequestRecord
from .probes.common import RequestLog


def latest_by_path() -> dict[str, RequestRecord]:
    latest: dict[str, RequestRecord] = {}
    for line in config.REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = RequestRecord.from_dict(json.loads(line))
        if record.evidence_path:
            latest[record.evidence_path] = record
    return latest


def target_name(url: str, suffix: str, digest: str) -> str:
    return _safe_name(url.split("?")[0], suffix, digest)


def suffix_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[name.rfind(".") :] if "." in name else ""


def _decoded_digest(blob: bytes) -> str:
    while blob[:2] == b"\x1f\x8b":
        blob = gzip.decompress(blob)
    return hashlib.sha256(blob).hexdigest()


def plan() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """(renames, duplicate_files, problems). Never mutates anything."""
    latest = latest_by_path()
    renames: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    problems: list[str] = []
    for path, record in sorted(latest.items()):
        if record.result == "evidence_retired":
            continue
        if evidence_manifest.is_content_addressed(path):
            continue
        source = config.REPO_ROOT / path
        if not source.exists():
            problems.append(f"source missing on disk: {path}")
            continue
        digest = record.sha256_decoded or record.sha256
        if not digest:
            problems.append(f"no recorded digest to address this file by: {path}")
            continue
        suffix = suffix_of(path)
        new_name = target_name(record.url, suffix, digest)
        if not new_name or new_name == path.rsplit("/", 1)[-1]:
            problems.append(f"cannot derive a new name for {path}")
            continue
        new_path = str((source.parent / new_name).relative_to(config.REPO_ROOT))
        if new_path == path:
            continue
        target = config.REPO_ROOT / new_path
        move = {
            "log_path": path,
            "current_path": new_path,
            "url": record.url,
            "sha256_decoded": digest,
            "size_bytes": source.stat().st_size,
        }
        if target.exists():
            if target.read_bytes() == source.read_bytes():
                move["identical"] = True
                duplicates.append(move)
            else:
                problems.append(
                    f"target exists with DIFFERENT bytes, refusing to touch: {new_path}"
                )
            continue
        renames.append(move)
    return renames, duplicates, problems


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    renames, duplicates, problems = plan()

    for problem in problems:
        print(f"PROBLEM: {problem}")
    if problems:
        print()
        print("refusing to migrate while there are unresolved problems.")
        return 1

    if not renames and not duplicates:
        print("every current evidence file is already content-addressed. nothing to do.")
        return 0

    print(f"{len(renames)} file(s) to rename to add a decoded-digest suffix:")
    for move in renames:
        print(f"  {move['log_path']}")
        print(f"    -> {move['current_path']}")
    print()
    print(f"{len(duplicates)} legacy file(s) are byte-identical duplicates of an "
          f"existing content-addressed file:")
    for move in duplicates:
        print(f"  {move['log_path']}")
        print(f"    identical to {move['current_path']}")

    if not apply:
        print()
        print("dry run. add --apply to rename, retire the duplicates, and write "
              "the manifest.")
        return 0

    log = RequestLog()
    entries: dict[str, dict[str, Any]] = {}
    migrated_utc = config.utc_now()

    for move in renames:
        source = config.REPO_ROOT / move["log_path"]
        target = config.REPO_ROOT / move["current_path"]
        source.rename(target)
        entries[move["log_path"]] = {
            "current_path": move["current_path"],
            "url": move["url"],
            "sha256_decoded": move["sha256_decoded"],
            "size_bytes": move["size_bytes"],
            "migrated_utc": migrated_utc,
            "action": "renamed",
            "reason": "legacy URL-only filename; renamed to the content-addressed "
            "scheme already used for evidence fetched after the fix. Bytes "
            "unchanged, request log untouched.",
        }
        print(f"renamed: {move['log_path']} -> {move['current_path']}")

    for move in duplicates:
        source = config.REPO_ROOT / move["log_path"]
        # Sanity: the digest of the file we are about to delete must match the
        # content-addressed twin's suffix, or this is not the duplicate it claims.
        on_disk = _decoded_digest(source.read_bytes())
        if on_disk != move["sha256_decoded"]:
            print(f"PROBLEM: {move['log_path']} content does not match its recorded "
                  f"digest; refusing to delete.", file=sys.stderr)
            return 1
        source.unlink()
        log.retire(
            move["log_path"],
            f"retired {migrated_utc}: byte-identical duplicate of "
            f"{move['current_path']}, which is retained. Deleted by "
            f"research/migrate_evidence.py; no HTTP request involved.",
        )
        entries[move["log_path"]] = {
            "current_path": move["current_path"],
            "url": move["url"],
            "sha256_decoded": move["sha256_decoded"],
            "size_bytes": move["size_bytes"],
            "migrated_utc": migrated_utc,
            "action": "retired_duplicate",
            "reason": "byte-identical duplicate of a content-addressed file that is "
            "retained; deleted and tombstoned rather than kept under a second name.",
        }
        print(f"retired duplicate: {move['log_path']}")

    # Carry forward any entries a previous run recorded, so the manifest stays
    # a complete map rather than a per-run delta.
    for path, entry in evidence_manifest.load_manifest().items():
        if (config.REPO_ROOT / entry.get("current_path", "")).exists():
            entries.setdefault(path, entry)

    written = evidence_manifest.write_manifest(
        entries,
        note="One-time evidence-name migration: legacy URL-only files renamed to the "
        "content-addressed scheme, and byte-identical duplicates retired with "
        "appended tombstones. Generated by research/migrate_evidence.py; existing "
        "request-log lines were not modified.",
    )
    print(f"manifest: {written.relative_to(config.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
