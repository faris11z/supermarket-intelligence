#!/usr/bin/env python3
"""Catch documentation that has drifted away from the evidence.

Every number in these reports was correct on the day it was written and then
went stale, usually because a later phase measured the same thing properly and
corrected the number without updating every copy of it. The same wrong figure
was repeated in four files at once, so a reader had no way to tell which copy to
believe.

This script makes that class of error loud. It does not check prose. It checks
that specific numbers the docs quote still match what the artefacts say, and
that a handful of phrases which were reversed by later evidence have not quietly
come back.

Usage:

    python research/check_docs_consistency.py           # human-readable
    python research/check_docs_consistency.py --strict  # non-zero exit on drift

Exit codes: 0 no drift, 1 drift found, 2 an input file is missing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH = REPO_ROOT / "data" / "research"
REPORTS = RESEARCH / "reports"

sys.path.insert(0, str(REPO_ROOT))

from research.models import is_replay_record  # noqa: E402 - path set up above

# Docs that quote shared numbers. Kept explicit rather than globbed so that a new
# document is a deliberate decision instead of an accident.
DOCS = [
    "README.md",
    "research/README.md",
    "timeline.md",
    "docs/research/beginner.md",
    "docs/research/phase-3-price-data-validation.md",
    "docs/research/supermarket-data-acquisition-spike.md",
    "docs/research/location-and-travel-feasibility.md",
    "docs/research/source-suitability-matrix.md",
]

# Phrases that were true once and were later disproved by measurement. If one of
# these reappears it is not necessarily an error, because each doc quotes the
# retracted claim while explaining the retraction, so matches are only failures
# when the surrounding line lacks a retraction marker.
RETRACTED = {
    "235 GET requests were made": "counts offline replays as real traffic; the real count is 117",
    "No explicit per-kg price field": "Aldi does publish basePrice; the parser read one dict level too shallow",
    "no unit-price comparison is possible from Aldi alone": "superseded: basePrice is published and now parsed",
    "GTIN-13 barcodes present": "measured 0 of 5 Lidl grocery pages; the Phase 1 hit was a wine page",
    "3,665 store-detail": "actual count is 3,270; 3,665 + 395 exceeded the 3,669 sitemap total",
    "no flour": "Lidl's catalog does contain two dinkelmehl SKUs",
    "Sanchia": "Lidl's own-brand is Solevita; Sanchia is not a Lidl brand",
    "Total HTTP requests:** 42": "access_log.json records 67 for Phase 1/2",
    "42 total, 5 product-detail pages": "correct totals are 67 requests and 7 product pages",
}
RETRACTION_MARKERS = (
    "correct",
    "wrong",
    "previously",
    "superseded",
    "overturned",
    "not a",
    "mistake",
    "retract",
    "conflated",
    "mistaken",
)


def load_report(name: str) -> dict[str, Any]:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def log_facts() -> dict[str, int]:
    records = [
        json.loads(line)
        for line in (RESEARCH / "request_log.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    real = [r for r in records if not is_replay_record(r) and r.get("method") == "GET"]
    return {
        "records": len(records),
        "real": len(real),
        "distinct": len({r["url"] for r in real}),
        "replay": sum(1 for r in records if is_replay_record(r)),
        "tombstones": sum(1 for r in records if r.get("result") == "evidence_retired"),
    }


class Findings:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def add(self, ok: bool, label: str, detail: str = "") -> None:
        self.rows.append((ok, label, detail))

    def report(self) -> int:
        print("=" * 74)
        print("DOCUMENTATION CONSISTENCY (offline, no network)")
        print("=" * 74)
        for ok, label, detail in self.rows:
            print(f"[{'ok  ' if ok else 'FAIL'}] {label}")
            if detail:
                print(f"       {detail}")
        failed = sum(1 for ok, _, _ in self.rows if not ok)
        print()
        print(f"{len(self.rows) - failed} passed, {failed} failed")
        if failed:
            print(
                "  A doc disagrees with the stored evidence. Fix the doc, or fix the\n"
                "  evidence and then the doc. Do not adjust the number to match the doc."
            )
        return failed


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    for doc in DOCS:
        if not (REPO_ROOT / doc).exists():
            print(f"missing document: {doc}", file=sys.stderr)
            return 2

    facts = log_facts()
    aldi = load_report("aldi.json")
    lidl = load_report("lidl.json")
    f = Findings()

    # The real request count is the number most often quoted wrongly, because the
    # log also contains one line per offline replay.
    f.add(
        facts["real"] == 117,
        "real request count is stable and matches the request log",
        f"{facts['real']} real GETs, {facts['replay']} replays, "
        f"{facts['tombstones']} tombstones, {facts['records']} records total. "
        f"Offline runs add replays only, so the real count is the one to quote.",
    )
    f.add(
        facts["records"] == facts["real"] + facts["replay"] + facts["tombstones"],
        "request log partitions into real + replay + tombstones",
        f"{facts['real']} + {facts['replay']} + {facts['tombstones']} = {facts['records']}",
    )
    f.add(
        facts["distinct"] == 53,
        "distinct URL count matches the request log",
        f"{facts['distinct']} distinct real URLs",
    )

    # Phase 1/2 accounting, which the spike doc understated.
    spike_log = json.loads(
        (REPO_ROOT / "data/raw/spike/access_log.json").read_text(encoding="utf-8")
    )
    total_12 = spike_log["_provenance"]["total_requests"]
    pages_12 = spike_log["_provenance"]["product_detail_pages_fetched"]
    f.add(
        total_12 == 67 and pages_12 == 7,
        "Phase 1/2 request totals match access_log.json",
        f"{total_12} requests, {pages_12} product pages (docs previously said 42 and 5)",
    )

    # Aldi: the basePrice finding that was reversed.
    priced = [o for o in aldi.get("observations", []) if o.get("price_eur") is not None]
    with_unit = [o for o in priced if o.get("unit_price_eur") is not None]
    f.add(
        bool(with_unit),
        "Aldi report contains published unit prices",
        f"{len(with_unit)} of {len(priced)} priced products carry a basePrice "
        f"({sorted({(o['unit_price_eur'], o.get('unit_price_basis')) for o in with_unit})}). "
        "A report with none would mean the nesting bug is back.",
    )
    f.add(
        not any(o.get("gtin") for o in aldi.get("observations", [])),
        "Aldi report contains no GTINs",
        "the no-barcode finding still holds; do not let it drift without evidence",
    )

    # Lidl: the three claims that were reversed.
    verification = lidl.get("product_verification", {})
    f.add(
        verification.get("pages_with_gtin") == 0,
        "Lidl grocery pages publish no GTIN, contradicting the Phase 1 claim",
        f"{verification.get('pages_with_gtin')} of {verification.get('pages_checked')} "
        "pages; Phase 1's 'GTIN-13 barcodes present' came from a wine page",
    )
    f.add(
        verification.get("pages_with_price") == 0,
        "Lidl grocery pages publish no price",
        f"{verification.get('pages_with_price')} of {verification.get('pages_checked')} pages",
    )
    grocery = lidl.get("catalog_analysis", {}).get("grocery_survivors", [])
    has_flour = [s for s in grocery if "mehl" in s]
    f.add(
        len(has_flour) == 2,
        "Lidl catalog does contain flour, contradicting the Phase 1 claim",
        f"{len(grocery)} grocery SKUs survive classification, of which flour: {has_flour}",
    )

    # Retracted phrases, allowing for the line that explains the retraction.
    for doc in DOCS:
        text = (REPO_ROOT / doc).read_text(encoding="utf-8")
        for phrase, why in RETRACTED.items():
            for lineno, line in enumerate(text.splitlines(), start=1):
                if phrase not in line:
                    continue
                context = line.lower()
                if any(marker in context for marker in RETRACTION_MARKERS):
                    continue
                # A doc that explains the correction in an adjacent line is fine.
                window = "\n".join(text.splitlines()[max(0, lineno - 3) : lineno + 2]).lower()
                if any(marker in window for marker in RETRACTION_MARKERS):
                    continue
                f.add(
                    False,
                    f"retracted claim reappears without a correction: {doc}:{lineno}",
                    f'"{phrase}" -- {why}',
                )
    f.add(
        True,
        f"scanned {len(DOCS)} documents for {len(RETRACTED)} retracted claims",
        "a claim quoted inside a passage that explains the retraction is allowed",
    )

    failed = f.report()
    return 1 if (failed and strict) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
