"""Shared helpers: the request log, robots handling, sitemap parsing.

The robots handling is the important part. This project treats robots.txt as a
hard gate, not a suggestion: if a path is disallowed for our user-agent we do
not request it at all, and we record that we skipped it and why.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from .. import config
from ..http_client import fetch, polite_sleep
from ..models import (
    REPLAY_NOTE_PREFIX,
    RequestRecord,
    RESULT_EVIDENCE_RETIRED,
    RESULT_NOT_FETCHED,
    SitemapStats,
)

# --------------------------------------------------------------------------
# Request log
# --------------------------------------------------------------------------


class RequestLog:
    """Append-only JSONL sink. One object per line, as specified."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.REQUEST_LOG
        self.records: list[RequestRecord] = []

    def add(self, record: RequestRecord) -> RequestRecord:
        self.records.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json() + "\n")
        return record

    def fetch(self, url: str, source: str, **kwargs: Any) -> tuple[RequestRecord, bytes | None]:
        record, body = fetch(url, source, **kwargs)
        self.add(record)
        return record, body

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for record in self.records:
            out[record.result] = out.get(record.result, 0) + 1
        return out

    def blocked(self) -> list[RequestRecord]:
        return [r for r in self.records if r.result == "blocked"]

    def replays(self) -> list[RequestRecord]:
        return [r for r in self.records if r.replayed or r.notes.startswith(REPLAY_NOTE_PREFIX)]

    def retire(self, evidence_path: str, reason: str, source: str = "retirement") -> RequestRecord:
        """Append a tombstone for an evidence file that was deleted on purpose.

        `python -m research.retire_evidence` is the intended caller. The point of
        a tombstone is that a reader hitting a log line whose evidence_path no
        longer exists can tell "removed on purpose" from "lost", and a tombstone
        with no reason defeats that.
        """
        record = RequestRecord(
            timestamp_utc=config.utc_now(),
            source=source,
            url="",
            method="DELETE",
            status_code=None,
            content_type=None,
            response_bytes=None,
            final_url=None,
            redirect_chain=[],
            result=RESULT_EVIDENCE_RETIRED,
            notes=reason,
            evidence_path=evidence_path,
        )
        return self.add(record)


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------


class RobotsGate:
    """Loads and evaluates a site's robots.txt for our own user-agent.

    A disallow decision is final. We do not fetch the URL to "see what happens",
    because that would be probing a path we have already been told not to use.

    The gate fails CLOSED. An unreachable or unreadable robots.txt is not
    permission; it is silence, and the previous version of this class returned
    True in that case, which quietly converted a missing rule into consent. The
    only exception is a named open-data service in
    `config.ROBOTS_EXEMPT_SOURCES`, which publishes a documented API and an
    explicit licence. That exemption is recorded per source in the report.
    """

    def __init__(
        self,
        log: RequestLog,
        robots_url: str,
        source: str,
        *,
        exempt: bool = False,
        exempt_reason: str = "",
    ) -> None:
        self.log = log
        self.robots_url = robots_url
        self.source = source
        self.origin = f"{urlparse(robots_url).scheme}://{urlparse(robots_url).netloc}"
        self.parser = RobotFileParser()
        self.fetched = False
        self.exempt = exempt
        self.exempt_reason = exempt_reason
        self.status: int | None = None
        self.sha256: str | None = None
        self.raw: str = ""
        self.decisions: dict[str, tuple[bool, str]] = {}

    @classmethod
    def exempt_gate(cls, log: RequestLog, source: str, reason: str) -> "RobotsGate":
        """A gate for a licensed open-data API, recorded rather than assumed.

        Made without fetching robots.txt, because spending a request against a
        shared public endpoint (Nominatim allows one request per second in
        absolute terms) to collect a rule that a published licence already
        settles is not worth the load.
        """
        return cls(log, "", source, exempt=True, exempt_reason=reason)

    def load(self) -> "RobotsGate":
        if self.exempt:
            return self
        record, body = self.log.fetch(
            self.robots_url, self.source, notes="robots.txt gate check"
        )
        self.fetched = True
        self.status = record.status_code
        self.sha256 = record.sha256
        if body and record.status_code == 200:
            self.raw = body.decode("utf-8", errors="replace")
            self.parser.parse(self.raw.splitlines())
        polite_sleep()
        return self

    def decision(self, url: str) -> tuple[bool, str]:
        """(allowed, human reason). Memoised, so the report can show the reasons."""
        if url in self.decisions:
            return self.decisions[url]
        verdict = self._decide(url)
        self.decisions[url] = verdict
        return verdict

    def allowed(self, url: str) -> bool:
        return self.decision(url)[0]

    def fetch(
        self, url: str, *, notes: str = "", save_body: bool = True
    ) -> tuple[RequestRecord, bytes | None]:
        """Gate then fetch, recording either outcome.

        Every probe goes through this rather than calling the log directly, so
        "did we respect robots.txt here?" is answered by the code path and not by
        remembering to call the gate. For an exempt source the decision is a
        recorded constant; if the exemption is ever withdrawn, the request stops
        instead of silently continuing.
        """
        allowed, reason = self.decision(url)
        if not allowed:
            return (
                self.log.add(
                    RequestRecord(
                        timestamp_utc=config.utc_now(),
                        source=self.source,
                        url=url,
                        method="GET",
                        status_code=None,
                        content_type=None,
                        response_bytes=None,
                        final_url=None,
                        redirect_chain=[],
                        result=RESULT_NOT_FETCHED,
                        notes=reason,
                    )
                ),
                None,
            )
        return self.log.fetch(url, self.source, notes=notes, save_body=save_body)

    def _decide(self, url: str) -> tuple[bool, str]:
        if self.exempt:
            return True, f"EXEMPT: {self.exempt_reason}"
        if not self.fetched:
            return False, "NOT FETCHED: robots.txt was never loaded; refusing to assume permission"
        if self.status != 200:
            return False, (
                f"NOT FETCHED: robots.txt returned {self.status}; a site that does not "
                "publish a usable robots.txt has not granted permission"
            )
        if self.parser.can_fetch(config.USER_AGENT, url):
            return True, "allowed by robots.txt"
        return False, "disallowed by robots.txt"

    def skipped(self) -> list[dict[str, str]]:
        return [
            {"url": url, "reason": reason}
            for url, (allowed, reason) in self.decisions.items()
            if not allowed
        ]

    def disallowed_paths(self) -> list[str]:
        if not self.raw:
            return []
        return [
            line.split(":", 1)[1].strip()
            for line in self.raw.splitlines()
            if line.lower().strip().startswith("disallow:")
            and line.split(":", 1)[1].strip()
        ]

    def sitemaps(self) -> list[str]:
        if not self.raw:
            return []
        return re.findall(
            r"^\s*sitemap:\s*(\S+)", self.raw, flags=re.IGNORECASE | re.MULTILINE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "robots_url": self.robots_url,
            "status_code": self.status,
            "sha256": self.sha256,
            "reachable": self.status == 200,
            "disallow_paths": self.disallowed_paths(),
            "declared_sitemaps": self.sitemaps(),
            "policy": "exempt: licensed open-data API" if self.exempt else "hard gate, fails closed",
            "exempt_reason": self.exempt_reason,
            "skipped_urls": self.skipped(),
        }


# --------------------------------------------------------------------------
# Sitemap parsing
# --------------------------------------------------------------------------

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)


def parse_sitemap(
    log: RequestLog,
    url: str,
    source: str,
    *,
    notes: str = "",
    gate: RobotsGate | None = None,
) -> tuple[SitemapStats, list[str], RequestRecord | None]:
    """Fetch and count a sitemap. Returns exact counts only, never estimates."""
    if gate is not None and not gate.allowed(url):
        allowed, reason = gate.decision(url)
        stats = SitemapStats(
            url=url,
            status_code=None,
            content_type=None,
            sha256=None,
            loc_count=0,
            is_index=False,
            notes=f"NOT FETCHED: {reason}",
        )
        return stats, [], None

    record, body = log.fetch(url, source, notes=notes)
    polite_sleep()

    if not body or record.status_code != 200:
        return (
            SitemapStats(
                url=url,
                status_code=record.status_code,
                content_type=record.content_type,
                sha256=record.sha256,
                loc_count=0,
                is_index="sitemapindex" in (body or b"").decode("utf-8", "replace"),
                notes=f"not retrievable (result={record.result})",
            ),
            [],
            record,
        )

    text = body.decode("utf-8", errors="replace")
    is_index = "sitemapindex" in text
    locs = [m.strip() for m in _LOC_RE.findall(text)]

    stats = SitemapStats(
        url=url,
        status_code=record.status_code,
        content_type=record.content_type,
        sha256=record.sha256,
        loc_count=len(locs),
        is_index=is_index,
        child_sitemaps=locs if is_index else [],
        sample_locs=locs[:5] if not is_index else [],
    )
    return stats, locs, record


# --------------------------------------------------------------------------
# HTML / JSON-LD helpers
# --------------------------------------------------------------------------

_SCRIPT_LD_RE = re.compile(
    r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def iter_jsonld(body: bytes) -> Iterable[dict[str, Any]]:
    """Yield parsed JSON-LD objects. Malformed blocks are skipped, not fatal."""
    text = body.decode("utf-8", errors="replace")
    for raw in _SCRIPT_LD_RE.findall(text):
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, dict):
                yield item


def next_data(body: bytes) -> dict[str, Any] | None:
    """Extract the __NEXT_DATA__ payload without executing JavaScript."""
    text = body.decode("utf-8", errors="replace")
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        text,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


_STYLE_SCRIPT_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(body: bytes | str) -> str:
    """Readable text from HTML, without executing anything.

    This is a crude text extraction, not a renderer. It is used to answer one
    narrow question: did the server send the words, or is the page a shell that
    expects JavaScript? A near-empty result is itself a finding.
    """
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    text = _STYLE_SCRIPT_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&auml;", "a"),
        ("&ouml;", "o"),
        ("&uuml;", "u"),
        ("&Auml;", "A"),
        ("&Ouml;", "O"),
        ("&Uuml;", "U"),
        ("&szlig;", "ss"),
        ("&euro;", "EUR"),
    ):
        text = text.replace(entity, char)
    return _WS_RE.sub(" ", text).strip()


def text_from_next_data(body: bytes) -> str | None:
    """Flatten the __NEXT_DATA__ JSON into searchable text, or None if absent.

    Useful when the interesting strings live in a nested payload rather than in
    rendered markup. Deliberately returns the raw JSON text too, so a caller
    can confirm the payload actually carried content rather than a null shell.
    """
    payload = next_data(body)
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_jsonl(path: Path, rows: Iterable[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path
