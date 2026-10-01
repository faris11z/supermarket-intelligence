"""Data models for the Phase 3 research harness.

Deliberately dependency-free (dataclasses + stdlib) so the harness has no
install step and can be audited by reading it.

The RequestRecord is the contract that data/research/request_log.jsonl must
satisfy. Field names match the Phase 3 brief exactly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical result values. Anything not in this set is a bug.
RESULT_SUCCESS = "success"
RESULT_BLOCKED = "blocked"
RESULT_REDIRECT = "redirect"
RESULT_ERROR = "error"
RESULT_NOT_FETCHED = "not_fetched"
# Written when an evidence file is deliberately deleted. The log is append-only,
# so a deletion has to be recorded too. Otherwise the log points at a file that
# no longer exists, and a reader cannot tell "removed on purpose" from "lost".
RESULT_EVIDENCE_RETIRED = "evidence_retired"

VALID_RESULTS = frozenset(
    {
        RESULT_SUCCESS,
        RESULT_BLOCKED,
        RESULT_REDIRECT,
        RESULT_ERROR,
        RESULT_NOT_FETCHED,
        RESULT_EVIDENCE_RETIRED,
    }
)

# Marks a log line produced by offline replay rather than by a network request.
REPLAY_NOTE_PREFIX = "offline replay"


def is_replay_record(data: dict[str, Any]) -> bool:
    """True when a log line describes an offline replay, not a real request.

    This distinction is the reason the request accounting in the reports had to
    be corrected: `run_probe --offline` appends one log line per URL it replays,
    and without this test those lines are indistinguishable from real requests.
    New records carry an explicit `replayed` flag; lines written before that flag
    existed are recognised by their notes prefix, so the existing log can be
    accounted for correctly without being rewritten.
    """
    if data.get("replayed") is True:
        return True
    return str(data.get("notes") or "").startswith(REPLAY_NOTE_PREFIX)


@dataclass
class RequestRecord:
    """One HTTP GET, fully described.

    Serialised as a single line of request_log.jsonl.
    """

    timestamp_utc: str
    source: str
    url: str
    method: str
    status_code: int | None
    content_type: str | None
    response_bytes: int | None
    final_url: str | None
    redirect_chain: list[str]
    result: str
    notes: str = ""
    # Extra provenance that does not fit the minimum schema.
    sha256: str | None = None
    # sha256 over the DECODED body, when the wire body was compressed. Kept
    # separate from sha256 so the record describes both what crossed the
    # network and what was actually parsed.
    sha256_decoded: str | None = None
    decoded_bytes: int | None = None
    decompress_rounds: int | None = None
    elapsed_ms: int | None = None
    evidence_path: str | None = None
    error: str | None = None
    # True when this line was written by an offline replay rather than by a
    # network request. Nothing else in the record implies it.
    replayed: bool = False

    def __post_init__(self) -> None:
        if self.result not in VALID_RESULTS:
            raise ValueError(f"invalid result {self.result!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RequestRecord":
        """Rebuild a record from a request-log line.

        Unknown keys are ignored rather than raising, so a log written by a
        newer version of the harness can still be replayed by an older one.
        """
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_json(self) -> str:
        """Compact single-line JSON, no NaN, stable key order."""
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=False)

    def summary(self) -> str:
        return f"[{self.result:>10}] {self.status_code!s:>4}  {self.source:<22} {self.url}"


@dataclass
class SitemapStats:
    """Counts extracted from a sitemap or sitemap index. All exact, never inferred."""

    url: str
    status_code: int | None
    content_type: str | None
    sha256: str | None
    loc_count: int
    is_index: bool
    child_sitemaps: list[str] = field(default_factory=list)
    sample_locs: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductObservation:
    """Normalized product record, comparable across sources.

    This is the Phase 8 schema. Fields left None are genuinely absent at the
    source; they are never inferred or back-filled.
    """

    source: str
    product_id: str | None = None
    gtin: list[str] = field(default_factory=list)
    name: str | None = None
    brand: str | None = None
    quantity: float | None = None
    unit: str | None = None
    category: str | None = None
    price_eur: float | None = None
    strike_price_eur: float | None = None
    promo_label: str | None = None
    unit_price_eur: float | None = None
    unit_price_basis: str | None = None
    availability: str | None = None
    structured_data_type: str | None = None
    source_url: str | None = None
    evidence_sha256: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LicensingFinding:
    """Structured licensing observation.

    Fields are deliberately conservative. `conclusion` is only ever
    "permitted", "prohibited", or "unresolved". Absence of a prohibition is
    never recorded as permission.
    """

    source: str
    date_utc: str
    documents_checked: list[dict[str, Any]] = field(default_factory=list)
    explicit_reuse_permission_found: bool = False
    licence_found: bool = False
    terms_found: bool | None = None
    terms_url: str | None = None
    terms_addresses_data_reuse: bool | None = None
    database_rights_discussed: str = "unknown"
    api_developer_terms_found: bool | None = None
    conclusion: str = "unresolved"
    legal_advice_required: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AlternativeSourceProbe:
    """One candidate open data source and the result of actually testing it."""

    name: str
    url: str
    data_type: str
    product_data: str
    price_data: str
    store_data: str
    gtin: str
    historical_prices: str
    geography: str
    licence: str
    commercial_reuse: str
    api_available: str
    rate_limits: str
    coverage: str
    freshness: str
    access_test_result: str = "not_run"
    access_test_detail: str = ""
    evidence_sha256: str | None = None
    licence_evidence_sha256: str | None = None
    live_total: int | None = None
    row_container_key: str | None = None
    sample_row_keys: list[str] | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
