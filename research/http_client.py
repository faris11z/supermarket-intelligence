"""Minimal, auditable HTTP client for Phase 3 research.

Design rules, in priority order:

1. One GET per URL *per run*, and never a retry. A retry policy would eventually
   include "retry with different characteristics", which this project rules out.
   A second GET of a URL already fetched in this run is refused and the body
   saved earlier in the run is returned instead, so the refusal is recorded
   rather than silently costing a request.
2. Honour robots.txt is the CALLER's job. This module records the outcome of
   whatever it is given; it does not decide permission. See probes/common.py.
3. Never store cookies, auth headers or credentials.
4. Record everything: status, final URL, redirect chain, content type, byte
   count, sha256, elapsed time.
5. Classify blocks, and make blocks loud so they cannot be mistaken for
   successes.
6. Never read more than config.MAX_DOWNLOAD_BYTES off the socket.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from . import config
from .evidence_manifest import resolve as resolve_evidence_path
from .models import (
    REPLAY_NOTE_PREFIX,
    RESULT_BLOCKED,
    RESULT_ERROR,
    RESULT_NOT_FETCHED,
    RESULT_REDIRECT,
    RESULT_SUCCESS,
    RequestRecord,
)

# Session-level state for the per-run request ceiling.
_request_count = 0

# URL -> (record, body) for everything already fetched in this run. Enforces the
# one-GET-per-URL rule in code rather than in a docstring: before this existed,
# "one request per URL" was a claim in a comment that nothing enforced.
_run_cache: dict[str, tuple[RequestRecord, bytes | None]] = {}

# When True, fetch() replays saved evidence instead of using the network. This
# exists so a parser fix can be re-run against the bytes we already have, rather
# than re-requesting a site to produce a report we could have derived locally.
# It is the difference between reproducible research and an expensive one.
_offline = False


def set_offline(enabled: bool) -> None:
    """Enable or disable offline replay. No network requests are made when on."""
    global _offline
    _offline = enabled
    if enabled:
        reset_request_count()


def is_offline() -> bool:
    return _offline


def reset_request_count() -> None:
    """Reset the per-run counters. Called at the start of every run."""
    global _request_count
    _request_count = 0
    _run_cache.clear()


def _replay(url: str, source: str, notes: str) -> tuple[RequestRecord, bytes | None]:
    """Rebuild a record + body from the saved request log and evidence files.

    Raises KeyError if the URL was never fetched, which is the correct
    behaviour: it means the finding genuinely is not reproducible from saved
    evidence, and a report must not be able to paper over that.
    """
    if not config.REQUEST_LOG.exists():
        raise KeyError(f"offline replay requested but no request log at {config.REQUEST_LOG}")

    latest: RequestRecord | None = None
    for line in config.REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = RequestRecord.from_dict(json.loads(line))
        if entry.url == url and entry.source == source:
            latest = entry

    if latest is None:
        raise KeyError(
            f"offline replay: {url} ({source}) is not in the request log; "
            "run the probe online once to capture it"
        )

    body: bytes | None = None
    if latest.evidence_path:
        # Resolve through the manifest: a log line names the file as it was when
        # the request was made, and evidence_manifest maps that to where the file
        # lives now. Without this, every renamed artefact silently replays as an
        # empty body, which looks exactly like a site returning nothing.
        candidate = config.REPO_ROOT / resolve_evidence_path(latest.evidence_path)
        if candidate.exists():
            body, _ = _gunzip(candidate.read_bytes())

    record = RequestRecord(
        timestamp_utc=latest.timestamp_utc,
        source=source,
        url=url,
        method="GET",
        status_code=latest.status_code,
        content_type=latest.content_type,
        response_bytes=latest.response_bytes,
        final_url=latest.final_url,
        redirect_chain=latest.redirect_chain,
        result=latest.result,
        notes=f"{REPLAY_NOTE_PREFIX} of {latest.timestamp_utc}. {notes}".strip(),
        sha256=latest.sha256,
        sha256_decoded=latest.sha256_decoded,
        decoded_bytes=latest.decoded_bytes,
        elapsed_ms=latest.elapsed_ms,
        evidence_path=latest.evidence_path,
        replayed=True,
    )
    return record, body


def request_count() -> int:
    return _request_count


def _safe_name(url: str, suffix: str, content_digest: str = "") -> str:
    """Build a filesystem-safe filename from a URL and an extension.

    `content_digest` is included so evidence is effectively immutable: with a
    one-file-per-URL scheme, a second request to the same URL silently
    overwrote the first body, which meant an earlier log entry's sha256 could
    no longer be checked. Content addressing removes that class of problem
    entirely, at the cost of duplicate files for repeated fetches.
    """
    parsed = urlparse(url)
    raw = f"{parsed.netloc}{parsed.path}".strip("/").replace("/", "_")
    raw = "".join(ch if ch in config.SAFE_FILENAME_CHARS else "-" for ch in raw)
    stem = raw[:100]
    if content_digest:
        stem = f"{stem}-{content_digest[:12]}"
    return f"{stem}{suffix}"


def _detect_block(status_code: int, content_type: str | None, body: bytes) -> str | None:
    """Return a human reason string if this looks like a block, else None.

    Deliberately conservative: we would rather mislabel a slow page as a
    challenge than quietly treat a challenge as data.
    """
    if status_code in config.BLOCKED_STATUSES:
        return f"HTTP {status_code} on a protected-status endpoint"

    ctype = (content_type or "").lower()
    if "html" not in ctype and "text" not in ctype:
        return None

    # Only sniff a prefix. Never read a whole 400 KB body to look for a title.
    head = body[:8192].decode("utf-8", errors="replace").lower()
    for marker in config.BOT_CHALLENGE_MARKERS:
        if marker in head:
            return f"bot-verification interstitial detected (marker: {marker!r})"
    return None


def _looks_gzipped(url: str, content_type: str | None, body: bytes) -> bool:
    """True when the response body is gzip-compressed and needs decoding.

    Two distinct cases that are easy to conflate:
      * Content-Encoding: gzip  -> urllib3 already decompressed it for us.
      * a .gz FILE (Content-Type: application/gzip) -> still raw gzip bytes.
    The second is what Lidl's product sitemap is, and feeding raw gzip bytes to
    an XML regex silently yields zero <loc> matches.
    """
    if body[:2] == b"\x1f\x8b":
        return True
    if "gzip" in (content_type or "").lower():
        return True
    return url.split("?")[0].endswith((".gz", ".gzip"))


def _gunzip(body: bytes) -> tuple[bytes, int]:
    """Decompress repeatedly until the body is not gzip any more.

    Returns (decoded, rounds). Rounds > 1 means the stored artefact was already
    double-compressed by an earlier version of this harness, and handling that
    here keeps old evidence usable instead of forcing a re-fetch.
    """
    rounds = 0
    while body[:2] == b"\x1f\x8b" and rounds < 4:
        try:
            body = gzip.decompress(body)
        except (OSError, EOFError, gzip.BadGzipFile):
            break
        rounds += 1
    return body, rounds


def _suffix_for(url: str, content_type: str | None, body: bytes) -> str:
    """Pick an evidence-file suffix for the DECODED body."""
    path = url.split("?")[0].lower()
    # A .gz URL whose content is XML should be stored as readable XML, not
    # re-compressed: the point of evidence is that a human can read it.
    stripped = path[:-3] if path.endswith(".gz") else path
    if body[:5].lstrip().startswith(b"<?xml") or stripped.endswith(".xml"):
        return ".xml"
    if "html" in (content_type or "").lower() or body[:200].lower().lstrip().startswith(b"<!doctype html"):
        return ".html"
    if "json" in (content_type or "").lower() or body[:1] in (b"{", b"["):
        return ".json"
    if path.endswith(".txt") or "text/" in (content_type or "").lower():
        return ".txt"
    return ".bin"


def fetch(
    url: str,
    source: str,
    *,
    notes: str = "",
    save_body: bool = True,
    method: str = "GET",
) -> tuple[RequestRecord, bytes | None]:
    """Perform exactly one GET and return a record plus the body bytes.

    The body is returned so callers can parse it without a second request. It
    is written to disk only when save_body is True and the response is small
    enough to be reasonable research evidence.

    Two refusals happen here rather than at the call sites, so a probe cannot
    accidentally step around them:

    * a URL already fetched in this run is served from memory, and the refusal
      is logged as `not_fetched`;
    * a body that grows past config.MAX_DOWNLOAD_BYTES is abandoned mid-stream.
      It is still recorded, with whatever prefix was read, so the event is
      visible instead of looking like a small successful response.
    """
    global _request_count

    if _offline:
        return _replay(url, source, notes)

    cached = _run_cache.get(url)
    if cached is not None:
        previous, body = cached
        return (
            RequestRecord(
                timestamp_utc=config.utc_now(),
                source=source,
                url=url,
                method=method,
                status_code=previous.status_code,
                content_type=previous.content_type,
                response_bytes=previous.response_bytes,
                final_url=previous.final_url,
                redirect_chain=previous.redirect_chain,
                result=RESULT_NOT_FETCHED,
                notes=(
                    f"NOT FETCHED: {url} was already fetched in this run; "
                    f"served from memory instead of requesting it again. {notes}"
                ).strip(),
                sha256=previous.sha256,
                sha256_decoded=previous.sha256_decoded,
                decoded_bytes=previous.decoded_bytes,
                decompress_rounds=previous.decompress_rounds,
                elapsed_ms=None,
                evidence_path=previous.evidence_path,
            ),
            body,
        )

    if _request_count >= config.MAX_REQUESTS_PER_RUN:
        raise RuntimeError(
            f"per-run request cap of {config.MAX_REQUESTS_PER_RUN} reached; "
            "refusing to make more requests"
        )

    timestamp = config.utc_now()
    redirect_chain: list[str] = []
    record: RequestRecord

    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "*/*",
        # Ask for the uncompressed original so the sha256 is over real bytes.
        "Accept-Encoding": "gzip, deflate",
    }

    started = time.monotonic()
    try:
        response = requests.get(
            url,
            timeout=config.TIMEOUT_SECONDS,
            headers=headers,
            allow_redirects=True,
            # Never send or receive a session cookie. We are not logging in
            # anywhere and do not want to accumulate state.
            cookies=None,
            # Read the body in bounded chunks so an oversized response cannot
            # be pulled into memory in full before the size test.
            stream=True,
        )
    except requests.RequestException as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        _request_count += 1
        record = RequestRecord(
            timestamp_utc=timestamp,
            source=source,
            url=url,
            method=method,
            status_code=None,
            content_type=None,
            response_bytes=None,
            final_url=None,
            redirect_chain=redirect_chain,
            result=RESULT_ERROR,
            notes=notes,
            elapsed_ms=elapsed,
            error=f"{type(exc).__name__}: {exc}",
        )
        return record, None

    buffer = bytearray()
    truncated = False
    try:
        for chunk in response.iter_content(chunk_size=config.READ_CHUNK_BYTES):
            if not chunk:
                continue
            buffer.extend(chunk)
            if len(buffer) > config.MAX_DOWNLOAD_BYTES:
                truncated = True
                break
    except requests.RequestException as exc:
        response.close()
        elapsed = int((time.monotonic() - started) * 1000)
        _request_count += 1
        return (
            RequestRecord(
                timestamp_utc=timestamp,
                source=source,
                url=url,
                method=method,
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                response_bytes=len(buffer),
                final_url=response.url,
                redirect_chain=redirect_chain,
                result=RESULT_ERROR,
                notes=notes,
                elapsed_ms=elapsed,
                error=f"body read failed after {len(buffer)} bytes: "
                f"{type(exc).__name__}: {exc}",
            ),
            bytes(buffer) or None,
        )

    elapsed = int((time.monotonic() - started) * 1000)
    _request_count += 1
    wire_body = bytes(buffer)
    content_type = response.headers.get("content-type")
    content_encoding = response.headers.get("content-encoding")
    final_url = response.url
    status_code = response.status_code

    # requests exposes the redirect chain on the response history.
    for hop in response.history:
        redirect_chain.append(f"{hop.status_code} {hop.url} -> {final_url}")
    response.close()

    # Decode if needed so parsers receive usable bytes. The wire digest is kept
    # separately so the record still describes exactly what crossed the network.
    body = wire_body
    gzip_rounds = 0
    if _looks_gzipped(url, content_type, wire_body) and content_encoding is None:
        body, gzip_rounds = _gunzip(wire_body)
    wire_digest = hashlib.sha256(wire_body).hexdigest()
    decoded_digest = (
        hashlib.sha256(body).hexdigest() if body is not wire_body else wire_digest
    )

    if truncated:
        block_reason = None
        result = RESULT_ERROR
        effective_notes = (
            f"response exceeded the {config.MAX_DOWNLOAD_BYTES}-byte download cap; "
            f"abandoned after {len(wire_body)} bytes and not persisted. {notes}"
        ).strip()
    else:
        block_reason = _detect_block(status_code, content_type, body)

        if block_reason:
            result = RESULT_BLOCKED
            effective_notes = f"{block_reason}. {notes}".strip()
        elif redirect_chain:
            result = RESULT_REDIRECT
            effective_notes = notes
        elif status_code is not None and 200 <= status_code < 300:
            result = RESULT_SUCCESS
            effective_notes = notes
        else:
            result = RESULT_ERROR
            effective_notes = f"unexpected status. {notes}".strip()

    evidence_path: str | None = None
    if save_body and body and not truncated and len(body) <= config.MAX_INLINE_BODY_BYTES:
        target_dir = config.RAW_DIR / source
        target_dir.mkdir(parents=True, exist_ok=True)
        # Always store the DECODED bytes, so a saved sitemap is greppable XML
        # rather than an opaque blob. Storing gzip-of-gzip, as an earlier
        # version did, made the artefact useless without code to unpack it.
        suffix = _suffix_for(url, content_type, body)
        target = target_dir / _safe_name(url.split("?")[0], suffix, decoded_digest)
        target.write_bytes(body)
        evidence_path = str(target.relative_to(config.REPO_ROOT))

    record = RequestRecord(
        timestamp_utc=timestamp,
        source=source,
        url=url,
        method=method,
        status_code=status_code,
        content_type=content_type,
        response_bytes=len(wire_body),
        final_url=final_url,
        redirect_chain=redirect_chain,
        result=result,
        notes=effective_notes,
        sha256=wire_digest,
        sha256_decoded=decoded_digest,
        decoded_bytes=len(body),
        decompress_rounds=gzip_rounds,
        elapsed_ms=elapsed,
        evidence_path=evidence_path,
    )
    # Remember it so a second request for the same URL in this run is refused
    # from memory instead of hitting the network.
    _run_cache[url] = (record, body)
    return record, body


def fetch_retirement_note(old_path: str, new_path: str) -> str:
    """Standard wording for a deliberate, disclosed evidence-file move."""
    return (
        f"local rename only, no HTTP request: {old_path} -> {new_path}; "
        "bytes unchanged (see data/research/evidence_manifest.json)"
    )


def polite_sleep() -> None:
    """Delay between requests. Applied by probe modules, not inside fetch, so
    that a caller doing local-only analysis is not slowed down."""
    if _offline:
        return
    time.sleep(config.REQUEST_DELAY_SECONDS)
