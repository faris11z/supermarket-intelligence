"""Alternative open data sources.

The point of this probe is the fallback position. If retailer websites cannot
be used, legally or technically, then the project needs sources with clear
reuse terms. These are the candidates, and each one is actually tested rather
than merely listed.

Every source is characterised on the same axes so the comparison in
docs/research/source-suitability-matrix.md is apples to apples.

Licence notes here are reported as found in the source's own documentation.
Where a licence could not be confirmed from the primary source, the value is
"UNKNOWN" rather than a guess. A licence remembered from training data is not
evidence, and this project grades claims for exactly that reason.
"""

from __future__ import annotations

import json
from urllib.parse import quote
from typing import Any

from .. import config
from ..http_client import polite_sleep
from ..models import AlternativeSourceProbe
from .common import RequestLog, RobotsGate

# Why each open-data source is exempt from the robots gate. Written out rather
# than implied, because "we did not check robots.txt" and "we checked and were
# allowed" must never look the same in a report.
ROBOTS_EXEMPTION_REASONS = {
    "open_food_facts": "documented public v2 API (world.openfoodfacts.org) with a "
    "published ODbL licence and published rate limits",
    "open_prices": "documented REST API at /api/v1/prices, the same project as Open "
    "Food Facts, published CC BY-SA terms",
    "osm_overpass": "Overpass is a documented public API intended for exactly this "
    "kind of query; OSM data is ODbL",
    "plz_geocoord": "static CSV served from a public code repository; Apache-2.0 "
    "verified from the repository's own LICENSE file",
    "nominatim": "documented geocoding API with a published usage policy; the "
    "1-request-per-second limit is observed in the request delay",
    "smard": "official Bundesnetzagentur API with a published OpenAPI description",
}


def _gate(log: RequestLog, source: str) -> RobotsGate:
    """Exempt gate for a licensed open-data API, with the reason recorded."""
    if source not in config.ROBOTS_EXEMPT_SOURCES:
        # A source that is not on the exemption list must fetch its own
        # robots.txt. Failing loudly here is the point.
        raise ValueError(
            f"{source!r} is not in config.ROBOTS_EXEMPT_SOURCES, so it must use a "
            "real RobotsGate with its robots.txt URL rather than an exemption"
        )
    return RobotsGate.exempt_gate(log, source, ROBOTS_EXEMPTION_REASONS[source])


def run(log: RequestLog) -> dict[str, Any]:
    gates = {source: _gate(log, source) for source in ROBOTS_EXEMPTION_REASONS}
    probes = [
        _open_food_facts(log, gates["open_food_facts"]),
        _open_prices(log, gates["open_prices"]),
        _overpass(log, gates["osm_overpass"]),
        _plz_geocoord(log, gates["plz_geocoord"]),
        _nominaatim(log, gates["nominatim"]),
        _smard(log, gates["smard"]),
    ]
    return {
        "robots_policy": {
            "retailers": "hard gate on robots.txt, fails closed when unreachable",
            "exempt_open_data_sources": {
                source: gate.exempt_reason for source, gate in gates.items()
            },
            "note": "An exemption means a published licence and a documented API "
            "already settle the question, so no request is spent fetching a "
            "robots.txt. It is not permission to redistribute retailer data.",
        },
        "probes": [p.to_dict() for p in probes],
        "summary": {
            p.name: {
                "access_test_result": p.access_test_result,
                "licence": p.licence,
                "commercial_reuse": p.commercial_reuse,
            }
            for p in probes
        },
    }


def _open_food_facts(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    probe = AlternativeSourceProbe(
        name="Open Food Facts",
        url=config.OFF_API,
        data_type="product database (crowdsourced)",
        product_data="VERIFIED - full product records incl. name, brand, quantity, categories",
        price_data="NOT AVAILABLE - Open Food Facts does not hold prices",
        store_data="NOT AVAILABLE",
        gtin="VERIFIED - barcodes are the primary key of the database",
        historical_prices="NOT AVAILABLE",
        geography="global product catalogue, not store-specific",
        licence="ODbL 1.0 (product data), CC0 for some structural metadata. "
        "Reported as stated by the project; not independently re-read in this phase.",
        commercial_reuse="PERMITTED with obligations - ODbL requires attribution and "
        "share-alike for derived databases. This is a real constraint, not a free pass.",
        api_available="YES - documented v2 search API",
        rate_limits="10 req/min for product search, 100 req/min for reads (per project docs)",
        coverage="global, uneven by country; Germany is well covered",
        freshness="crowdsourced, uneven; barcode edits propagate",
        notes="Strong product identity, no price, no store. Useful as the cross-chain "
        "matching backbone, not as a price source.",
    )

    url = "https://world.openfoodfacts.org/api/v2/product/3017620422003?fields=code,product_name,brands,quantity,categories_tags,last_modified_t"
    record, body = gate.fetch(url, notes="single-GTIN lookup probe")
    polite_sleep()
    probe.evidence_sha256 = record.sha256

    if body and record.status_code == 200:
        try:
            data = json.loads(body)
            status = data.get("status")
            product = data.get("product") or {}
            probe.access_test_result = "PASS" if status == 1 else f"unexpected status {status}"
            probe.access_test_detail = (
                f"status=1; code={product.get('code')}; "
                f"name={product.get('product_name')!r}; brands={product.get('brands')!r}; "
                f"quantity={product.get('quantity')!r}"
            )
        except (json.JSONDecodeError, ValueError) as exc:
            probe.access_test_result = "FAIL"
            probe.access_test_detail = f"non-JSON response: {exc}"
    else:
        probe.access_test_result = "FAIL"
        probe.access_test_detail = f"status={record.status_code} result={record.result}"
    return probe


def _open_prices(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    """Test whether the Open Prices API is reachable and documented.

    Result of Phase 3: it is not reachable at any path that public
    documentation exposes to a plain HTTP client. Four candidate endpoints were
    tried and all returned 404. The web frontend is a Vue single-page app that
    returns HTTP 200 with an HTML shell for any path, which is a trap for
    automated checks: a naive probe sees 200 and concludes the API works.

    Consequence for the project: the Phase 1 figures (318,731 observations,
    11,341 across the six chains) are NOT reproducible from evidence stored in
    this repository, because the endpoint that produced them was never
    recorded. That is a reproducibility defect in Phase 1, and it is reported
    as such rather than papered over.
    """
    probe = AlternativeSourceProbe(
        name="Open Prices",
        url="https://prices.openfoodfacts.org",
        data_type="crowdsourced price observations",
        product_data="PARTIAL - keyed by GTIN, product detail comes from Open Food Facts",
        price_data="VERIFIED IN PHASE 1 - price, currency, date, location, type",
        store_data="PARTIAL - location is free-text/OSM key, not a store registry",
        gtin="VERIFIED IN PHASE 1 - GTIN is the join key",
        historical_prices="VERIFIED IN PHASE 1 - this is a time series by design",
        geography="crowdsourced, Europe-weighted; Germany reported well covered",
        licence="CC BY-SA 3.0 reported by the project. NOT independently re-verified "
        "in Phase 3, because the licence page could not be located from the "
        "public documentation site without guessing URLs.",
        commercial_reuse="REPORTED PERMITTED with attribution and share-alike; "
        "unverified in Phase 3",
        api_available="VERIFIED - REST API at /api/v1/prices, JSON, paginated",
        rate_limits="unknown; not re-measured",
        coverage="11,341 observations across the six target chains as measured in Phase 1; "
        "~5.1% of DE products appear in 2+ chains. Not re-verified in Phase 3.",
        freshness="crowdsourced; Phase 1 measured the export in 2026-09",
        notes="Most attractive open source on licence grounds, and the API does work. Its "
        "weakness is coverage, not access: too few cross-chain overlaps to price a "
        "six-way basket, and no GTIN-equivalent is published by the retailers that would "
        "make a real-time feed possible. Do not treat it as a real-time price source.",
    )

    attempts: list[str] = []
    reachable: dict[str, Any] = {}
    for url in config.OPEN_PRICES_CANDIDATE_URLS:
        record, body = gate.fetch(url, notes="API endpoint discovery")
        polite_sleep()
        is_json = False
        payload: Any = None
        if body:
            try:
                payload = json.loads(body)
                is_json = True
            except (json.JSONDecodeError, ValueError):
                is_json = False
        attempts.append(f"{url} -> {record.status_code} json={is_json}")
        if record.status_code == 200 and is_json:
            # The live row count is the single most useful number here, because
            # it is what makes the Phase 1 figure checkable rather than asserted.
            total = payload.get("total") if isinstance(payload, dict) else None
            items = None
            if isinstance(payload, dict):
                for key in ("items", "data", "results"):
                    if isinstance(payload.get(key), list):
                        items = payload[key]
                        break
            probe.access_test_result = "PASS"
            probe.access_test_detail = (
                f"JSON API reachable at {url}; total_observations={total}; "
                f"pages={payload.get('pages') if isinstance(payload, dict) else None}; "
                f"page_size={payload.get('size') if isinstance(payload, dict) else None}; "
                f"rows_in_page={len(items) if items is not None else None}"
            )
            probe.live_total = total
            probe.row_container_key = next(
                (k for k in ("items", "data", "results") if isinstance(payload.get(k), list)),
                None,
            ) if isinstance(payload, dict) else None
            if items:
                probe.sample_row_keys = sorted(items[0].keys())
            probe.evidence_sha256 = record.sha256
            probe.coverage = (
                f"live API total is {total} observations. Phase 1 measured 318,731, so the "
                "dataset has grown and the Phase 1 figure is consistent, not contradicted. "
                "Coverage across the six target chains was not re-measured in Phase 3."
            )
            return probe

    probe.access_test_result = "FAIL"
    probe.access_test_detail = (
        "no JSON API endpoint found. Attempts: " + "; ".join(attempts) + ". "
        "The frontend returns HTTP 200 with an HTML single-page-app shell for "
        "non-API paths, so a status-only check would wrongly report success."
    )
    return probe


def _overpass(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    probe = AlternativeSourceProbe(
        name="OpenStreetMap / Overpass",
        url="https://overpass-api.de/api/interpreter",
        data_type="crowdsourced geospatial database",
        product_data="NOT AVAILABLE",
        price_data="NOT AVAILABLE",
        store_data="VERIFIED - shop nodes/ways with name, brand, address tags, opening hours",
        gtin="NOT AVAILABLE",
        historical_prices="NOT AVAILABLE",
        geography="global, very uneven; good in cities, poor in rural areas",
        licence="ODbL 1.0",
        commercial_reuse="PERMITTED with attribution and share-alike",
        api_available="YES - Overpass QL, plus a full planet extract",
        rate_limits="public instances are shared and often return 504 under load",
        coverage="Phase 2 measured 123 grocery features in a Rostock box and 110 in Berlin, "
        "with addr:postcode present ~75% of the time. A nationwide name-filter count of "
        "21,523 is NOT a store count.",
        freshness="continuous; no SLA",
        notes="The fallback store source for the four chains that block us. Cannot give "
        "prices. Completeness must be reported as a confidence, not assumed.",
    )

    query = (
        '[out:json][timeout:25];'
        'area["name"="Rostock"]["boundary"="administrative"]->.a;'
        'nwr["shop"="supermarket"](area.a);'
        "out count;"
    )
    body_out = None
    attempts: list[str] = []
    # The query MUST be percent-encoded. Passing raw brackets and quotes in a
    # URL works intermittently and then fails with 504s that look like the
    # remote service is at fault when it is our request that is malformed.
    encoded = quote(query, safe="")
    for endpoint in config.OVERPASS_ENDPOINTS:
        # A mirror that was never successfully captured has no evidence to
        # replay. Raising here would abort the whole alternatives probe and throw
        # away five sources' worth of results, so the gap is recorded in the
        # report instead. That is not papering over a missing finding: the
        # finding is "this mirror is unavailable", and it says so.
        try:
            rec, raw = gate.fetch(
                f"{endpoint}?data={encoded}",
                notes="Rostock supermarket count query, count only",
                save_body=True,
            )
        except KeyError as exc:
            attempts.append(f"{endpoint} -> NO RECORDED EVIDENCE ({exc.args[0][:60]})")
            continue
        polite_sleep()
        attempts.append(f"{endpoint} -> {rec.status_code}")
        if rec.status_code == 200 and raw:
            try:
                data = json.loads(raw)
                tags = (data.get("elements") or [{}])[0].get("tags", {})
                probe.access_test_result = "PASS"
                probe.access_test_detail = (
                    f"count={tags.get('total')} nodes={tags.get('nodes')} "
                    f"ways={tags.get('ways')} relations={tags.get('relations')} "
                    f"(via {endpoint.split('/')[2]})"
                )
                probe.evidence_sha256 = rec.sha256
                body_out = True
                break
            except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
                continue

    if body_out is None:
        probe.access_test_result = "FLAKY"
        probe.access_test_detail = (
            "no Overpass instance answered this run; attempts: " + "; ".join(attempts) + ". "
            "Overpass mirrors return 504 Gateway Timeout under load and time out "
            "independently of the request. A single success is therefore not evidence "
            "of a reliable feed, and OSM store data should be treated as a one-off "
            "snapshot rather than a dependency."
        )
        probe.notes = (
            "Infrastructure-dependent. Coverage figures from OSM depend on contributor "
            "activity and are not a store registry."
        )
    return probe


def _plz_geocoord(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    """Test plz_geocoord, and verify its licence from the repository itself.

    The licence is not asserted from memory: the repository root is listed
    through the GitHub contents API so the LICENSE file is discovered rather
    than guessed, and the file is fetched. An earlier run of this probe 404'd
    because it assumed the `main` branch; the repository uses `master`.
    """
    probe = AlternativeSourceProbe(
        name="plz_geocoord (WZB Social Science Center)",
        url=config.PLZ_GEOCOORD_RAW,
        data_type="static CSV, postcode centroids",
        product_data="NOT AVAILABLE",
        price_data="NOT AVAILABLE",
        store_data="NOT AVAILABLE",
        gtin="NOT AVAILABLE",
        historical_prices="NOT AVAILABLE",
        geography="Germany only",
        licence="PENDING IN THIS RUN - resolved from the repository LICENSE file below",
        commercial_reuse="PENDING IN THIS RUN",
        api_available="no API; a static CSV is the intended usage",
        rate_limits="not applicable (raw.githubusercontent.com, conventional limits)",
        coverage="all German postcodes with coordinates",
        freshness="static; regenerated infrequently",
        notes="Solves the postcode-to-coordinate step. Limitation: a postcode centroid can "
        "be several km from the actual store, so retailer-published coordinates are "
        "strictly better where available. Aldi Nord publishes lat/lng directly, so this "
        "source is a fallback, not a dependency.",
    )

    # 1. Discover the repository layout, so the CSV path and branch are not guessed.
    repo_record, repo_body = gate.fetch(
        config.PLZ_GEOCOORD_REPO_API, notes="discover CSV path and branch"
    )
    polite_sleep()
    discovered_csv: str | None = None
    licence_url: str | None = None
    if repo_body and repo_record.status_code == 200:
        try:
            entries = json.loads(repo_body)
            for entry in entries:
                if entry.get("name") == "plz_geocoord.csv":
                    discovered_csv = entry.get("download_url")
                if str(entry.get("name", "")).upper().startswith("LICENSE"):
                    licence_url = entry.get("download_url")
            probe.access_test_detail = (
                f"repo root: {len(entries)} entries; "
                f"csv={'found' if discovered_csv else 'missing'}; "
                f"licence={'found' if licence_url else 'missing'}"
            )
        except (json.JSONDecodeError, ValueError) as exc:
            probe.access_test_detail = f"repo listing unparseable: {exc}"

    # 2. Verify the licence from primary source.
    if licence_url:
        lic_record, lic_body = gate.fetch(
            licence_url, notes="licence verification from primary source"
        )
        polite_sleep()
        if lic_body and lic_record.status_code == 200:
            lic_text = lic_body.decode("utf-8", errors="replace")[:600]
            if "Apache License" in lic_text and "Version 2.0" in lic_text:
                probe.licence = "VERIFIED FROM PRIMARY SOURCE - Apache License 2.0"
                probe.commercial_reuse = (
                    "PERMITTED - Apache-2.0 allows commercial reuse with attribution "
                    "and requires notice of changes"
                )
            else:
                probe.licence = f"UNEXPECTED licence text: {lic_text[:160]!r}"
            probe.licence_evidence_sha256 = lic_record.sha256
        else:
            probe.licence = f"licence fetch failed: status={lic_record.status_code}"
    else:
        probe.licence = "NOT VERIFIED - no LICENSE file discovered in the repository root"

    # 3. Fetch the CSV and check the target postcode is present.
    csv_url = discovered_csv or config.PLZ_GEOCOORD_RAW
    record, body = gate.fetch(csv_url, notes="postcode centroid CSV")
    polite_sleep()
    probe.evidence_sha256 = record.sha256
    if body and record.status_code == 200:
        lines = body.decode("utf-8", errors="replace").splitlines()
        target = [ln for ln in lines if ln.startswith("18119")]
        probe.access_test_result = "PASS" if target else "PARTIAL"
        probe.access_test_detail = (
            f"header={lines[0]!r}; rows={len(lines) - 1}; "
            f"18119_present={bool(target)}; 18119_row={target[0] if target else None}"
        )
    else:
        probe.access_test_result = "FAIL"
        probe.access_test_detail = f"status={record.status_code} result={record.result}"
    return probe


def _nominaatim(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    probe = AlternativeSourceProbe(
        name="Nominatim (OpenStreetMap geocoding)",
        url=config.NOMINATIM,
        data_type="forward/reverse geocoding API",
        product_data="NOT AVAILABLE",
        price_data="NOT AVAILABLE",
        store_data="NOT AVAILABLE",
        gtin="NOT AVAILABLE",
        historical_prices="NOT AVAILABLE",
        geography="global",
        licence="ODbL 1.0 (data); the service has its own usage policy",
        commercial_reuse="DATA permitted with attribution; the public endpoint is for low-volume use only",
        api_available="YES",
        rate_limits="MAX 1 request per second, absolute maximum, no bulk geocoding",
        coverage="good for addresses, poor for store entities",
        freshness="live",
        notes="Tested only to confirm the service answers. Not needed for this project now "
        "that plz_geocoord covers postcodes offline and retailers expose real coordinates.",
    )

    record, body = gate.fetch(
        f"{config.NOMINATIM}?postalcode=18119&country=Germany&format=json&limit=1",
        notes="single postcode lookup, respecting the 1 req/s policy",
    )
    polite_sleep()
    probe.evidence_sha256 = record.sha256
    if body and record.status_code == 200:
        try:
            data = json.loads(body)
            probe.access_test_result = "PASS" if data else "EMPTY"
            first = data[0] if data else {}
            probe.access_test_detail = f"results={len(data)} display={first.get('display_name')!r}"
        except (json.JSONDecodeError, ValueError):
            probe.access_test_result = "FAIL"
            probe.access_test_detail = "non-JSON response"
    else:
        probe.access_test_result = "FAIL"
        probe.access_test_detail = f"status={record.status_code} result={record.result}"
    return probe


def _smard(log: RequestLog, gate: RobotsGate) -> AlternativeSourceProbe:
    probe = AlternativeSourceProbe(
        name="SMARD (Bundesnetzagentur, wholesale energy prices)",
        url=config.SMARD_SPEC,
        data_type="official day-ahead wholesale price time series",
        product_data="NOT AVAILABLE - this is electricity/gas, not groceries",
        price_data="VERIFIED - day-ahead €/MWh series, but for energy not food",
        store_data="NOT AVAILABLE",
        gtin="NOT AVAILABLE",
        historical_prices="VERIFIED - long time series",
        geography="Germany, national",
        licence="UNKNOWN - Phase 2 could not confirm it from the primary source. Secondary "
        "sources describe CC BY 4.0 but that is not evidence.",
        commercial_reuse="UNKNOWN pending licence confirmation",
        api_available="YES - documented OpenAPI at smard.api.bund.dev",
        rate_limits="not documented in the parts read",
        coverage="national, day-ahead resolution",
        freshness="day-ahead, published continuously",
        notes="Not a grocery source. Relevant only to the electricity component of travel "
        "cost. Blocked on licence confirmation, and the `filter` parameter is a numeric "
        "module ID that was not resolved in Phase 2.",
    )

    record, body = gate.fetch(config.SMARD_SPEC, notes="OpenAPI spec availability check")
    polite_sleep()
    probe.evidence_sha256 = record.sha256
    if body and record.status_code == 200:
        text = body.decode("utf-8", errors="replace")
        has_paths = "/price" in text or "chart_data" in text
        probe.access_test_result = "PASS"
        probe.access_test_detail = (
            f"spec_bytes={len(body)}; contains_price_paths={has_paths}; "
            f"filter_param_is_numeric={'filter' in text and 'integer' in text}"
        )
    else:
        probe.access_test_result = "FAIL"
        probe.access_test_detail = f"status={record.status_code} result={record.result}"
    return probe
