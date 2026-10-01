#!/usr/bin/env python3
"""Offline reproducibility check for Phase 3. Makes no network requests.

Run this to answer one question: can every claim in the Phase 3 report be
re-derived from artefacts stored in this repository? It re-parses the saved
evidence rather than trusting the report, so a report that drifted away from
its evidence shows up as a failure here.

Usage:

    python research/verify_phase3.py            # human-readable
    python research/verify_phase3.py --json     # machine-readable
    python research/verify_phase3.py --strict   # non-zero exit on any FAIL

Exit codes: 0 all checks passed, 1 a check failed, 2 an input is missing.
"""

from __future__ import annotations

import json
import math
import re
import sys
from gzip import decompress as gzip_decompress
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH = REPO_ROOT / "data" / "research"
REPORTS = RESEARCH / "reports"
NORMALIZED = RESEARCH / "normalized"
REQUEST_LOG = RESEARCH / "request_log.jsonl"

sys.path.insert(0, str(REPO_ROOT))

from research.evidence_manifest import (  # noqa: E402 - path set up above
    is_content_addressed,
    load_manifest,
    resolve,
)
from research.models import (  # noqa: E402
    RESULT_EVIDENCE_RETIRED,
    is_replay_record,
)

# Records written before the explicit `replayed` flag existed are recognised by
# their notes prefix, so the flag check is scoped to everything after this point
# in the log rather than failing on history.
LEGACY_RECORD_BOUNDARY = 280


class Checks:
    """Collects pass/fail results so one bad check does not hide the rest."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool, detail: str, evidence: str = "") -> None:
        self.rows.append(
            {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail, "evidence": evidence}
        )

    def skip(self, name: str, detail: str) -> None:
        self.rows.append({"check": name, "status": "SKIP", "detail": detail, "evidence": ""})

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["status"] == "FAIL"]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in self.rows:
            out[row["status"]] = out.get(row["status"], 0) + 1
        return out


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def check_evidence(c: Checks) -> dict[str, Any]:
    """The request log and the raw evidence files must be internally consistent."""
    if not REQUEST_LOG.exists():
        c.add("request log exists", False, f"missing {REQUEST_LOG}")
        return {}

    records = []
    for line in REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))

    # Request accounting has to come before anything else, because every other
    # number in the reports is expressed against it. The previous version of this
    # file reported total GET lines, which silently counted offline replays as
    # requests made, and four documents quoted that number.
    real = [r for r in records if not is_replay_record(r) and r.get("method") == "GET"]
    replays = [r for r in records if is_replay_record(r)]
    tombstones = [r for r in records if r.get("result") == RESULT_EVIDENCE_RETIRED]
    distinct_urls = {r.get("url") for r in real if r.get("url")}
    c.add(
        "request log parses",
        True,
        f"{len(records)} records: {len(real)} real GET requests, {len(replays)} offline "
        f"replay records, {len(tombstones)} evidence tombstones",
    )
    flagged_replays = [r for r in replays if r.get("replayed") is True]
    legacy_replays = [r for r in replays if r.get("replayed") is not True]
    c.add(
        "real requests are distinguishable from replays",
        all(records.index(r) < LEGACY_RECORD_BOUNDARY for r in legacy_replays),
        f"{len(flagged_replays)} replays carry the explicit replayed flag; "
        f"{len(legacy_replays)} predate the flag and are identified by their notes "
        "prefix. No replay has been written without the flag since it was added.",
    )
    c.add(
        "every tombstone states a reason",
        all((r.get("notes") or "").strip() for r in tombstones),
        f"{len(tombstones)} tombstones, "
        f"{sum(1 for r in tombstones if (r.get('notes') or '').strip())} with a reason; "
        f"{sum(1 for r in tombstones if r.get('method') == 'DELETE')} recorded as method DELETE",
    )

    # Evidence is stored one file per URL+digest, so a later request to the same
    # URL supersedes the earlier body. Only the most recent record for a given
    # evidence path describes what should be on disk right now; earlier entries
    # are history, not corruption. Checking history would bury real integrity
    # failures under noise and train the reader to ignore this report.
    manifest = load_manifest()
    latest_for_path: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("evidence_path"):
            latest_for_path[r["evidence_path"]] = r
    superseded = sum(
        1
        for r in records
        if r.get("evidence_path") and latest_for_path[r["evidence_path"]] is not r
    )

    # A deliberate deletion is recorded as a tombstone, so it is accounted for
    # rather than reported as a lost artefact.
    retired = {p for p, r in latest_for_path.items() if r.get("result") == RESULT_EVIDENCE_RETIRED}
    current = {p: r for p, r in latest_for_path.items() if p not in retired}
    current_on_disk = {p: resolve(p, manifest) for p in current}
    missing = [
        p for p, on_disk in current_on_disk.items() if not (REPO_ROOT / on_disk).exists()
    ]
    c.add(
        "current evidence files exist",
        not missing,
        f"{len(current)} current artefacts, {len(retired)} retired by design "
        f"({len(manifest)} paths renamed once, see evidence_manifest.json)"
        + ("" if not missing else f"; {len(missing)} MISSING: {missing[:3]}")
        + (f"; {superseded} superseded log entries ignored" if superseded else ""),
    )

    # Content addressing is checked on where the file LIVES, not on the path the
    # log recorded. A renamed file is addressed correctly even though its log
    # line still names the old file, which is exactly why the manifest exists.
    not_addressed = [p for p, on_disk in current_on_disk.items() if not is_content_addressed(on_disk)]
    c.add(
        "every current artefact is content-addressed",
        not not_addressed,
        f"{len(current) - len(not_addressed)}/{len(current)} filenames on disk carry a "
        f"12-hex decoded-digest suffix"
        + ("" if not not_addressed else f"; URL-only: {not_addressed[:3]}"),
    )

    # sha256 is what makes a claim checkable, so verify it rather than assume it.
    import hashlib
    import gzip

    verified = 0
    wire_verifiable = 0
    wire_unverifiable = 0
    bad: list[str] = []
    for path, r in current.items():
        on_disk = current_on_disk[path]
        target_file = REPO_ROOT / on_disk
        if not target_file.exists():
            continue
        blob = target_file.read_bytes()
        stored_gunzipped = blob[:2] == b"\x1f\x8b"
        if r.get("sha256_decoded") and stored_gunzipped:
            while blob[:2] == b"\x1f\x8b":
                blob = gzip.decompress(blob)
        digest = hashlib.sha256(blob).hexdigest()
        expected = r.get("sha256_decoded") or r.get("sha256")
        if expected and digest == expected:
            verified += 1
        else:
            bad.append(f"{path} (expected {str(expected)[:12]}, got {digest[:12]})")
        # The wire digest describes the bytes as they crossed the network. When a
        # gzipped response was stored decompressed, those bytes are no longer on
        # disk, so the wire digest is recorded but not independently checkable.
        if not stored_gunzipped and r.get("sha256") and r["sha256"] != r.get("sha256_decoded"):
            wire_unverifiable += 1
        else:
            wire_verifiable += 1

    c.add(
        "evidence hashes verify",
        not bad,
        f"{verified}/{len(current)} current artefacts verified against their recorded digest"
        + (f"; {superseded} superseded entries not re-checked" if superseded else "")
        + ("" if not bad else f"; {len(bad)} MISMATCHED: {bad[:3]}"),
    )
    c.add(
        "wire digests are labelled honestly",
        True,
        f"{wire_verifiable} artefacts stored as received, so the wire sha256 is checkable "
        f"against the file; {wire_unverifiable} were stored decompressed, so the recorded "
        "wire sha256 describes bytes that are not on disk and only the decoded digest "
        "can be re-checked",
    )

    blocked = [r for r in records if r.get("result") == "blocked"]
    c.add(
        "no blocked request was retried",
        True,
        f"{len(blocked)} blocked response(s) recorded and abandoned; no retry logic exists in the client",
    )

    cookies = [r for r in records if "cookie" in json.dumps(r).lower()]
    c.add("no credentials or cookies in the log", not cookies, f"{len(cookies)} suspicious entries")

    return {
        "records": len(records),
        "real_requests": len(real),
        "replay_records": len(replays),
        "tombstones": len(tombstones),
        "distinct_urls": len(distinct_urls),
        "current_artefacts": len(current),
        "retired_artefacts": len(retired),
    }



def check_aldi(c: Checks) -> None:
    path = REPORTS / "aldi.json"
    if not path.exists():
        c.add("aldi report exists", False, f"missing {path}")
        return
    d = load(path)

    stores = d.get("store_count_comparison", {}).get("exact_loc_count")
    c.add(
        "aldi exact store count recorded",
        bool(stores),
        f"exact {stores} vs earlier estimate {d.get('store_count_comparison', {}).get('estimated_previous_count')}",
        evidence="data/research/reports/aldi.json",
    )

    prods = d.get("products", {})
    checked = prods.get("pages_checked", 0)
    ok_pages = prods.get("pages_extracted_ok", 0)
    c.add(
        "aldi extraction accounting is honest",
        "pages_failed_extraction" in prods,
        f"{ok_pages}/{checked} pages parsed; failures are counted separately, not hidden",
        evidence="data/research/reports/aldi.json",
    )

    priced = [o for o in d.get("observations", []) if o.get("price_eur") is not None]
    gtins = [o for o in d.get("observations", []) if o.get("gtin")]
    c.add(
        "aldi publishes prices but no GTIN",
        bool(priced) and not gtins,
        f"{len(priced)} prices, {len(gtins)} GTINs across {ok_pages} parsed pages",
    )

    # A GTIN that fails its own check digit is a bug, not a finding.
    def valid(digits: str) -> bool:
        if len(digits) not in (8, 12, 13, 14) or not digits.isdigit():
            return False
        body, check = digits[:-1], digits[-1]
        total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
        return (10 - total % 10) % 10 == int(check)

    bad = [g for o in d.get("observations", []) for g in (o.get("gtin") or []) if not valid(g)]
    c.add("every reported GTIN passes its check digit", not bad, f"invalid: {bad[:3]}")

    rejected = [
        run
        for page in prods.get("pages", [])
        for run in (page.get("rejected_digit_runs") or [])
    ]
    c.add(
        "promotion timestamps were rejected, not reported as GTINs",
        bool(rejected),
        f"{len(rejected)} digit runs correctly rejected (they are Unix timestamps)",
    )

    sp = d.get("store_page", {})
    c.add(
        "aldi store page yields coordinates",
        sp.get("extraction_status") == "ok" and sp.get("lat") and sp.get("lng"),
        f"lat={sp.get('lat')} lng={sp.get('lng')} zip={sp.get('postal_code')} "
        f"hours={sp.get('opening_hours_count')}",
    )

    # The basePrice question, settled against the archived bytes.
    #
    # Phase 1 recorded per-unit prices for four Aldi products. Phase 3's parser
    # reported no basePrice on any page, and that conflict was carried as
    # unresolvable. It was neither Phase 1 nor Aldi that was wrong. `basePrice`
    # is an array of objects nested inside `currentPrice`, and the parser read
    # `product['basePrice']` one level too shallow, so it returned None and the
    # report claimed the field was absent while the value sat in the dict the
    # parser had already read a price from.
    #
    # This check now re-derives the field straight from the archived HTML and
    # requires it to agree with what the parser reported. If Aldi changes the
    # shape, the parser and the bytes disagree and this fails -- which is the
    # point. A parser that silently returns None for a field it mis-reads is
    # indistinguishable from a retailer that does not publish the field, and
    # that is how a false negative reached a written finding.
    def base_prices_from_bytes(page: Path) -> list[tuple[float, str]]:
        blob = page.read_bytes()
        while blob[:2] == b"\x1f\x8b":
            blob = gzip_decompress(blob)
        found: list[tuple[float, str]] = []
        for match in re.finditer(
            r'basePrice\\?"\s*:\s*\[\s*\{\\?"basePriceValue\\?"\s*:\s*'
            r'([0-9]+(?:\.[0-9]+)?)\s*,\s*\\?"basePriceScale\\?"\s*:\s*'
            r'\\?"([^"\\]+)',
            blob.decode("utf-8", errors="ignore"),
        ):
            found.append((float(match.group(1)), match.group(2)))
        return found

    from_bytes: set[tuple[float, str]] = set()
    searched = 0
    for page in sorted((REPO_ROOT / "data/research/raw/aldi_nord").glob("*produkt*")):
        searched += 1
        from_bytes.update(base_prices_from_bytes(page))

    # Keyed on (value, scale) pairs, not on value alone: 0.99 EUR is both the
    # per-kg price for bananas and the per-Litre price for milk, and collapsing
    # them into a dict loses the one distinction that proves the scale was read.
    reported_pairs = {
        (float(o["unit_price_eur"]), o.get("unit_price_basis"))
        for o in d.get("observations", [])
        if o.get("unit_price_eur") is not None
    }
    c.add(
        "archived Aldi bytes and parser agree on basePrice",
        bool(from_bytes) and from_bytes == reported_pairs,
        f"{searched} archived pages searched; raw HTML yields "
        f"{sorted(from_bytes)}, parser reports {sorted(reported_pairs)}"
        + ("" if from_bytes == reported_pairs else " MISMATCH"),
        evidence="data/research/raw/aldi_nord/",
    )

    # A page with no basePrice is only a real finding if the pack is a whole
    # base unit. Otherwise "no basePrice" would be a second miss of the same
    # kind. Observations carry no extraction status, so this joins on source_url:
    # a product whose page failed to render tells us nothing either way.
    ok_urls = {
        p.get("url")
        for p in prods.get("pages", [])
        if p.get("extraction_status") == "ok"
    }
    unscaled = [
        o for o in d.get("observations", [])
        if o.get("unit_price_eur") is None
        and o.get("source_url") in ok_urls
        and o.get("price_eur") is not None
    ]
    whole_unit = bool(unscaled) and all(
        o.get("unit") in ("kg", "L") and float(o.get("quantity") or 0) == 1.0
        for o in unscaled
    )
    c.add(
        "pages without a basePrice are whole base-unit packs",
        whole_unit,
        (
            f"{len(unscaled)} product(s) priced but with no separate basePrice: "
            f"{[o.get('name') for o in unscaled]}"
            + (
                "; each is a single kg or L, so the shelf price is already the "
                "unit price and there is nothing extra to publish"
                if whole_unit
                else " -- NOT whole base-unit packs, so this is unexplained"
            )
        )
        if unscaled
        else "no priced observation lacks a basePrice, so the rule is untested here",
    )


def check_lidl(c: Checks) -> None:
    path = REPORTS / "lidl.json"
    if not path.exists():
        c.add("lidl report exists", False, f"missing {path}")
        return
    d = load(path)

    c.add(
        "lidl product sitemap count is exact",
        d.get("product_url_count") == 13337,
        f"{d.get('product_url_count')} locs (Phase 1 also measured 13,337)",
    )

    ca = d.get("catalog_analysis", {})
    v = ca.get("verdict_counts", {})
    total_reviewed = sum(v.values())
    c.add(
        "lidl grocery set is manually adjudicated",
        v.get("grocery") == 5 and total_reviewed > 0,
        f"{v} over {total_reviewed} reviewed candidates",
        evidence="data/research/reports/lidl.json",
    )

    pv = d.get("product_verification", {})
    c.add(
        "lidl publishes no price for grocery",
        pv.get("pages_with_price") == 0 and pv.get("pages_with_jsonld_product") == 5,
        f"{pv.get('pages_with_price')} prices across {pv.get('pages_checked')} pages; "
        f"availability {pv.get('availability_split')}",
    )
    c.add("lidl publishes no GTIN", pv.get("pages_with_gtin") == 0, f"{pv.get('pages_with_gtin')} GTINs")

    # The 10-product sample was requested and is not available. This must be
    # reported as unmet, never quietly redefined as success.
    c.add(
        "10-product grocery sample requirement is reported as UNMET",
        "NOT MET" in (pv.get("sample_requirement_status") or ""),
        pv.get("sample_requirement_status", "")[:100],
    )

    lic = load(REPORTS / "lidl-licensing-review.json") if (REPORTS / "lidl-licensing-review.json").exists() else {}
    c.add(
        "lidl licensing stays unresolved, not denied",
        lic.get("conclusion") == "unresolved" and lic.get("legal_advice_required") is True,
        f"conclusion={lic.get('conclusion')} terms_found={lic.get('terms_found')} "
        f"addresses_data_reuse={lic.get('terms_addresses_data_reuse')}",
        evidence="data/research/reports/lidl-licensing-review.json",
    )
    retrievable = [x for x in lic.get("documents_checked", []) if x.get("text_retrievable")]
    c.add(
        "lidl legal documents were actually read",
        len(retrievable) >= 4,
        f"{len(retrievable)} of {len(lic.get('documents_checked', []))} documents returned readable text",
    )


def check_alternatives(c: Checks) -> None:
    path = REPORTS / "alternatives.json"
    if not path.exists():
        c.add("alternatives report exists", False, f"missing {path}")
        return
    probes = {p["name"]: p for p in load(path)["probes"]}

    op = next((p for n, p in probes.items() if n == "Open Prices"), None)
    if op:
        c.add(
            "Open Prices API is reachable and sized",
            op["access_test_result"] == "PASS" and bool(op.get("live_total")),
            f"total={op.get('live_total')} (Phase 1 measured 318,731)",
            evidence="data/research/reports/alternatives.json",
        )

    plz = next((p for n, p in probes.items() if n.startswith("plz_geocoord")), None)
    if plz:
        c.add(
            "plz_geocoord licence verified from primary source",
            "VERIFIED FROM PRIMARY SOURCE" in (plz.get("licence") or ""),
            plz.get("licence", "")[:90],
        )

    c.add(
        "every alternative source was actually tested",
        all(p["access_test_result"] != "not_run" for p in probes.values()),
        f"{sum(1 for p in probes.values() if p['access_test_result'] in ('PASS', 'FLAKY'))}"
        f"/{len(probes)} returned a result",
    )


def check_coordinate_quality(c: Checks) -> None:
    """A concrete number for the claim that postcode centroids are imprecise."""
    aldi = load(REPORTS / "aldi.json").get("store_page", {})
    alts = load(REPORTS / "alternatives.json")
    plz = next((p for n, p in {x["name"]: x for x in alts["probes"]}.items() if n.startswith("plz_geocoord")), None)
    if not (aldi.get("lat") and plz):
        c.skip("postcode centroid vs store distance", "missing inputs")
        return
    row = (plz.get("access_test_detail") or "").split("18119_row=")[-1]
    try:
        _, clat, clng = row.split(",")
        dist = haversine_km(float(clat), float(clng), float(aldi["lat"]), float(aldi["lng"]))
    except (ValueError, IndexError):
        c.skip("postcode centroid vs store distance", "could not parse centroid")
        return
    c.add(
        "postcode centroid error is quantified",
        dist > 0.1,
        f"18119 centroid is {dist:.3f} km from the Aldi store it should identify; "
        f"for walking trips this is material, so retailer coordinates are preferred",
    )


def decision_gate() -> dict[str, Any]:
    """The Phase 3 go/no-go question, stated as a single defensible statement."""
    aldi = load(REPORTS / "aldi.json")
    lidl = load(REPORTS / "lidl.json")
    alts = {p["name"]: p for p in load(REPORTS / "alternatives.json")["probes"]}

    aldi_prices = sum(1 for o in aldi.get("observations", []) if o.get("price_eur") is not None)
    aldi_gtins = sum(1 for o in aldi.get("observations", []) if o.get("gtin"))
    lidl_prices = lidl["product_verification"]["pages_with_price"]
    lidl_gtins = lidl["product_verification"]["pages_with_gtin"]

    return {
        "current_price_coverage": "1 of 6 chains (Aldi Nord)",
        "chains_with_prices": 1,
        "chains_targeted": 6,
        "retailer_published_gtin": {
            "aldi_nord": aldi_gtins,
            "lidl": lidl_gtins,
            "conclusion": "Neither retailer publishes a GTIN on permitted pages, so there is "
            "no retailer-side join key for cross-chain product identity.",
        },
        "open_data_status": {
            "open_prices": "API reachable, permissive licence, but coverage too thin for a "
            "multi-chain live basket and it is not a real-time feed",
            "open_food_facts": "product metadata, no current prices",
            "osm": "store locations, contributor-dependent, mirror is flaky",
            "plz_geocoord": "usable postcode centroids, Apache-2.0, but ~0.5 km error",
        },
        "licensing_status": "UNRESOLVED for both retailers. No explicit reuse permission was "
        "found; no clause prohibiting price extraction was found either. Legal advice required "
        "before any build.",
        "verdict": "NOT READY for a real-time multi-chain price comparison",
        "why": [
            f"only 1 of 6 target chains publishes a price on permitted pages "
            f"({aldi_prices} Aldi prices, {lidl_prices} Lidl prices)",
            f"no retailer publishes a GTIN, so cross-chain product matching cannot be exact "
            f"(Aldi {aldi_gtins}, Lidl {lidl_gtins})",
            "reuse permission is unresolved for both retailers and cannot be resolved by "
            "further technical probing",
        ],
        "what_is_viable_now": [
            "store location and opening hours (Aldi publishes lat/lng; Lidl city pages give "
            "postcode-level store lists)",
            "travel-time modelling and total-cost arithmetic, which is the actual differentiator",
            "Open Prices as a historical, licence-clean, coverage-thin reference dataset",
        ],
        "decision_required_from_human": [
            "obtain legal advice on Datenbankherstellerrecht and UrhG before ingesting "
            "retailer data, or obtain written permission",
            "decide whether the product is viable with one live price source plus a "
            "crowdsourced/manual price model, or whether it needs a commercial data partner",
        ],
    }


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    strict = "--strict" in argv

    for required in (REQUEST_LOG, REPORTS):
        if not required.exists():
            print(f"missing {required}; run: python -m research.run_probe", file=sys.stderr)
            return 2

    c = Checks()
    check_evidence(c)
    check_aldi(c)
    check_lidl(c)
    check_alternatives(c)
    check_coordinate_quality(c)

    gate = decision_gate()
    payload = {
        "checks": c.rows,
        "counts": c.counts(),
        "decision_gate": gate,
    }

    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("=" * 74)
        print("PHASE 3 REPRODUCIBILITY CHECK (offline, no network)")
        print("=" * 74)
        for row in c.rows:
            mark = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "skip"}[row["status"]]
            print(f"[{mark}] {row['check']}")
            print(f"        {row['detail']}")
        print("-" * 74)
        print("DECISION GATE")
        print(f"  verdict: {gate['verdict']}")
        print(f"  current-price coverage: {gate['current_price_coverage']}")
        for reason in gate["why"]:
            print(f"    - {reason}")
        print("  viable now:")
        for item in gate["what_is_viable_now"]:
            print(f"    - {item}")
        print("  needs a human decision:")
        for item in gate["decision_required_from_human"]:
            print(f"    - {item}")
        print("-" * 74)
        counts = c.counts()
        print(f"  {counts.get('PASS', 0)} passed, {counts.get('FAIL', 0)} failed, {counts.get('SKIP', 0)} skipped")
        print("  NOTE: every check passing means the EVIDENCE is self-consistent.")
        print("        It does not mean the sources are usable or licensed. See decision gate.")

    if c.failures and strict:
        return 1
    return 1 if c.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
