"""Map every log evidence_path to where that file actually lives now.

The problem this solves. Phase 3 fetched some URLs before evidence was
content-addressed, so those files are named after the URL alone
(`www.lidl.de_p_export_..._product_sitemap.xml.gz.xml`). 41 of the 58 current
artefacts were in that state. Content addressing was then added, and 17 files
were re-fetched into digest-suffixed names, leaving both an old URL-only file
and a new digest-suffixed file for the same URL.

Two ways to fix that were considered:

  1. Rename the legacy files and rewrite `evidence_path` in the request log.
     This gives one uniform naming scheme, but it edits an append-only log. The
     log is the record of what was requested, and mutating a pointer inside it
     is exactly the kind of quiet edit this project refuses to make.
  2. Leave the log alone and keep a separate, regenerable index.

This module implements (2). `data/research/evidence_manifest.json` is derived
state: it can be deleted and rebuilt at any time, it is never the source of
truth, and it exists so that a log line written in September can still be
resolved to the file on disk today. `migrate_evidence.py` does the renaming and
writes the manifest; `verify_phase3.py` resolves paths through it.

The manifest also records which artefacts are content-addressed, so a reader can
see the naming history instead of having to infer it from filenames.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config

MANIFEST_PATH = config.DATA_ROOT / "evidence_manifest.json"

DIGEST_SUFFIX_CHARS = 12


def digest_suffix(path: str) -> str:
    """The 12-hex decoded-digest suffix of a content-addressed filename, or ''."""
    stem = Path(path).stem
    tail = stem.rsplit("-", 1)[-1]
    if len(tail) == DIGEST_SUFFIX_CHARS and all(c in "0123456789abcdef" for c in tail):
        return tail
    return ""


def is_content_addressed(path: str) -> bool:
    return bool(digest_suffix(path))


def load_manifest(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """log evidence_path -> entry. Missing manifest means "no moves recorded"."""
    target = path or MANIFEST_PATH
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload.get("entries", {})


def resolve(log_path: str, manifest: dict[str, dict[str, Any]] | None = None) -> str:
    """Where the file for this log entry lives now. Falls back to the log path."""
    entries = load_manifest() if manifest is None else manifest
    entry = entries.get(log_path)
    if not entry:
        return log_path
    return entry.get("current_path", log_path)


def write_manifest(entries: dict[str, dict[str, Any]], note: str = "") -> Path:
    payload = {
        "generated_utc": config.utc_now(),
        "purpose": "Derived index from request-log evidence_path to the file on "
        "disk. Regenerable with `python -m research.migrate_evidence`; never the "
        "source of truth.",
        "note": note,
        "entries": entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return MANIFEST_PATH
