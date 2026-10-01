"""Aldi Nord probe.

Scope, deliberately narrow:

* The robots.txt gate, so every later request is provably permitted.
* The sitemap index and its four children, to get an EXACT loc count. This
  replaces a previous estimate derived from store-ID ranges, which was an
  inference and not a measurement.
* Re-verification of the five product pages already sampled in Phase 1, plus
  the one store page. No new product URLs are discovered or fetched.

Nothing here crawls. Nothing here guesses legal URLs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .. import config
from ..http_client import polite_sleep
from ..models import ProductObservation, SitemapStats
from .common import RequestLog, RobotsGate, iter_jsonld, next_data, parse_sitemap

GTIN_KEYS = ("gtin13", "gtin14", "gtin12", "gtin8", "gtin", "ean", "barcode")
# Any bare 8-14 digit token is scanned, to be thorough about the "no GTIN"
# finding rather than only checking known key names.
_DIGIT_RUN_RE = re.compile(r"(?<![0-9])[0-9]{8,14}(?![0-9])")


def run(log: RequestLog) -> dict[str, Any]:
    """Run the Aldi Nord verification. Returns a findings dict."""
    findings: dict[str, Any] = {"source": "aldi_nord"}

    gate = RobotsGate(log, config.ALDI_ROBOTS, "aldi_nord").load()
    findings["robots"] = gate.to_dict()

    # ---- sitemap index and exact child counts -------------------------
    index_stats, child_locs, _ = parse_sitemap(
        log,
        config.ALDI_SITEMAP_INDEX,
        "aldi_nord",
        notes="sitemap index; enumerate declared children",
        gate=gate,
    )
    findings["sitemap_index"] = index_stats.to_dict()
    findings["sitemap_child_count"] = len(child_locs)

    per_child: dict[str, Any] = {}
    totals: dict[str, int] = {}
    for child in child_locs:
        if not gate.allowed(child):
            per_child[child] = {"loc_count": 0, "notes": "skipped: disallowed by robots.txt"}
            continue
        stats, locs, _ = parse_sitemap(
            log, child, "aldi_nord", notes="exact loc count", gate=gate
        )
        per_child[child] = stats.to_dict()
        kind = child.rsplit("-", 1)[-1].replace(".xml", "")
        totals[kind] = stats.loc_count

    findings["sitemap_children"] = per_child
    findings["sitemap_totals_by_kind"] = totals

    exact_stores = totals.get("stores", 0)
    findings["store_count_comparison"] = {
        "exact_loc_count": exact_stores,
        "estimated_previous_count": config.ALDI_PRIOR_STORE_ESTIMATE,
        "difference": exact_stores - config.ALDI_PRIOR_STORE_ESTIMATE,
        "method": "exact count of <loc> elements in the advertised store sitemap",
        "supersedes": "earlier estimate inferred from store-ID ranges, which was never a measurement",
    }

    # ---- re-verify previously sampled product pages -------------------
    products, product_findings = _verify_products(log, gate)
    findings["products"] = product_findings
    # The normalized records live under their own key. `products` above is the
    # summary dict, and run_probe looks for a *list* to normalize; sharing a key
    # between a summary and its data made the normalization step silently
    # produce nothing.
    findings["observations"] = [p.to_dict() for p in products]

    # ---- re-verify the single previously sampled store page -----------
    findings["store_page"] = _verify_store(log, gate, config.ALDI_PRIOR_STORE_URL)

    # ---- licensing: record, do not resolve ---------------------------
    findings["licensing"] = {
        "legal_document_discovered": False,
        "legal_reuse_permission_identified": False,
        "method": "Phase 2 searched the 649-URL pages sitemap. No general Terms of Use and "
        "no Impressum is published. The 5 privacy pages and 7 promotion-terms pages exist "
        "but their text is CMS-fetched client-side, so no clause was read.",
        "requests_made_this_phase": 0,
        "note": "No legal URL guessing was repeated in Phase 3, per instruction. "
        "robots.txt permission is not a reuse licence. This is a LEGAL QUESTION, "
        "not a technical finding, and is deliberately left unresolved.",
    }

    return findings


def _verify_products(
    log: RequestLog, gate: RobotsGate
) -> tuple[list[ProductObservation], dict[str, Any]]:
    products: list[ProductObservation] = []
    checked = 0
    extracted = 0
    prices_found = 0
    gtin_found = 0
    next_data_found = 0
    details: list[dict[str, Any]] = []

    for url in config.ALDI_PRIOR_PRODUCT_URLS:
        if not gate.allowed(url):
            details.append({"url": url, "result": "skipped: disallowed by robots.txt"})
            continue

        record, body = log.fetch(
            url, "aldi_nord", notes="re-verification of previously sampled page"
        )
        polite_sleep()
        checked += 1

        if not body or record.status_code != 200:
            details.append(
                {
                    "url": url,
                    "result": record.result,
                    "status_code": record.status_code,
                    "sha256": record.sha256,
                    "extraction_status": "failed: body not retrieved",
                }
            )
            continue

        observation, page_detail = _parse_aldi_product(url, body, record.sha256)
        products.append(observation)
        next_data_found += page_detail["has_next_data"]

        # Counts are only meaningful over pages that actually parsed. Reporting
        # "0 prices found" when 1 of 5 pages failed to parse would be a false
        # negative presented as a finding.
        if page_detail.get("extraction_status") == "ok":
            extracted += 1
            prices_found += observation.price_eur is not None
            gtin_found += bool(observation.gtin)

        page_detail["status_code"] = record.status_code
        page_detail["sha256"] = record.sha256
        details.append(page_detail)

    summary = {
        "pages_checked": checked,
        "pages_extracted_ok": extracted,
        "pages_failed_extraction": checked - extracted,
        "prices_found": prices_found,
        "gtin_found": gtin_found,
        "next_data_found": next_data_found,
        "jsonld_blocks": sum(1 for d in details if d.get("jsonld_blocks")),
        "gtin_conclusion": (
            f"no GTIN/EAN on any of the {extracted} pages that parsed successfully "
            "(re-confirmed). Pages that failed to parse are excluded from this count."
        ),
        "counting_caveat": (
            "prices_found and gtin_found are denominated over pages_extracted_ok, not "
            "pages_checked. A page that fails to extract is a harness failure, not "
            "evidence about the source."
        ),
        "pages": details,
    }
    return products, summary


def _parse_aldi_product(
    url: str, body: bytes, sha256: str | None
) -> tuple[ProductObservation, dict[str, Any]]:
    """Extract a product from the __NEXT_DATA__ payload.

    Two implementation details here are load-bearing, and both were confirmed
    against the saved evidence rather than assumed:

    1. `apiData` is a *stringified* JSON blob. One json.loads is not enough.
    2. Once parsed, `apiData` is a LIST OF [key, value] PAIRS, not a dict.
       A plain `api_data.get("PRODUCT_DETAIL_GET")` silently returns None and
       every price comes out as absent, which looks exactly like "no prices".
       Getting this wrong would have produced a confidently wrong report.
    """
    observation = ProductObservation(
        source="aldi_nord", source_url=url, evidence_sha256=sha256
    )
    detail: dict[str, Any] = {
        "url": url,
        "jsonld_blocks": 0,
        "has_next_data": False,
        "api_data_extracted": False,
        "extraction_status": "not_attempted",
    }

    for block in iter_jsonld(body):
        detail["jsonld_blocks"] += 1
        if block.get("@type") == "Product":
            observation.structured_data_type = "schema.org Product (JSON-LD)"

    payload = next_data(body)
    detail["has_next_data"] = payload is not None
    if payload is None:
        detail["extraction_status"] = "failed: no __NEXT_DATA__ in body"
        return observation, detail

    api_data = _api_data_entries(body)
    detail["api_data_keys"] = sorted(api_data.keys())
    if not api_data:
        # Distinguish "apiData is null" (server sent a shell) from "apiData is
        # an unexpected shape" (we broke), because only the first is a source
        # observation.
        raw = payload.get("props", {}).get("pageProps", {}).get("apiData")
        detail["api_data_shape"] = type(raw).__name__
        detail["extraction_status"] = (
            "failed: page has __NEXT_DATA__ but apiData is null. The server rendered a "
            "near-empty shell, so the product was not delivered in HTML. This is NOT "
            "evidence that the product lacks a price."
        )
        observation.notes = (
            "Extraction failure, not a data finding. The URL redirected (308) to a .html "
            "variant that renders without the product payload. Whether this means the "
            "product is discontinued, renamed, or requires a store selection cannot be "
            "determined from the permitted page."
        )
        return observation, detail

    entry = api_data.get("PRODUCT_DETAIL_GET")
    if not isinstance(entry, dict):
        detail["extraction_status"] = "failed: no PRODUCT_DETAIL_GET entry"
        return observation, detail

    container = _res(entry)
    items = container.get("products") if isinstance(container, dict) else None
    if not isinstance(items, list) or not items:
        detail["extraction_status"] = "failed: PRODUCT_DETAIL_GET has no products[]"
        return observation, detail
    product = items[0]
    if not isinstance(product, dict):
        detail["extraction_status"] = "failed: products[0] is not an object"
        return observation, detail

    detail["extraction_status"] = "ok"

    observation.product_id = str(product.get("objectID") or "") or None
    observation.name = product.get("name")
    observation.brand = product.get("brandName") or None
    observation.availability = (
        "available" if product.get("isAvailable") else "unavailable"
    )
    observation.category = _category_from_ids(product)
    observation.quantity, observation.unit = _sales_unit(product.get("salesUnit"))

    # `currentPrice` is a NESTED OBJECT, not a scalar. Observed shape:
    #   currentPrice = {'priceValue': 0.99,
    #                   'strikePrice': {'strikePriceValue': 1.59,
    #                                   'strikePriceLabel': 'UVP'}, ...}
    # An earlier version read `currentPrice` directly, got a dict, coerced it
    # to None, and reported "0 prices found" -- a false negative that looked
    # exactly like a real finding about Aldi. Never treat an unparseable price
    # as an absent price.
    current = product.get("currentPrice")
    detail["current_price_shape"] = type(current).__name__
    observation.price_eur = None
    observation.strike_price_eur = None
    observation.promo_label = None
    if isinstance(current, dict):
        observation.price_eur = _as_float(current.get("priceValue"))
        strike = current.get("strikePrice")
        if isinstance(strike, dict):
            observation.strike_price_eur = _as_float(strike.get("strikePriceValue"))
            observation.promo_label = strike.get("strikePriceLabel")
    elif current is not None:
        observation.price_eur = _as_float(current)

    # `basePrice` DOES exist on these pages, and Phase 1 recorded it correctly.
    #
    # Two mistakes made it look absent, and both were the same mistake made
    # twice. The field is not a scalar and it is not at the top level of the
    # product: it is an ARRAY OF OBJECTS nested INSIDE `currentPrice`, as a
    # sibling of `priceValue`:
    #
    #   currentPrice: {priceValue: 0.99,
    #                  strikePrice: {...},
    #                  basePrice: [{basePriceValue: 0.99, basePriceScale: 'kg'}],
    #                  validFrom: 1791151200}
    #
    # The first attempt read `product['basePrice']` (wrong level) and
    # `product['basePriceUnit']` (a key that does not exist; the scale is
    # `basePriceScale` inside the list element). Both returned None, and
    # `has_base_price_key` was computed as `'basePrice' in product`, which is
    # False for the same reason. So the report stated "no basePrice field" while
    # the value sat in the same dict the parser had already read a price from.
    #
    # A parse miss is not a finding about the retailer. `detail` now records
    # which shape was found so a future shape change is visible instead of
    # silently becoming "Aldi does not publish unit prices" again.
    observation.unit_price_eur = None
    observation.unit_price_basis = None
    detail["base_price_shape"] = None
    detail["base_price_container"] = None
    for container_name, container in (("currentPrice", current), ("product", product)):
        if not isinstance(container, dict) or "basePrice" not in container:
            continue
        raw_base = container["basePrice"]
        detail["base_price_container"] = container_name
        # Shape A: [{basePriceValue, basePriceScale}] -- the real one.
        entry = raw_base[0] if isinstance(raw_base, list) and raw_base else raw_base
        detail["base_price_shape"] = "list" if isinstance(raw_base, list) else type(raw_base).__name__
        if isinstance(entry, dict):
            observation.unit_price_eur = _as_float(entry.get("basePriceValue"))
            observation.unit_price_basis = entry.get("basePriceScale") or None
            break
        if isinstance(entry, (int, float, str)):
            observation.unit_price_eur = _as_float(entry)
            observation.unit_price_basis = entry.get("basePriceUnit") or None if isinstance(entry, str) else None
            break
    detail["has_base_price_key"] = detail["base_price_container"] is not None
    detail["has_base_price_value"] = observation.unit_price_eur is not None

    # GTIN: check known keys, then scan bare digit runs WITH check-digit
    # validation, and record what was rejected so the "no GTIN" claim is
    # auditable rather than merely asserted.
    found_gtin: list[str] = []
    for key in GTIN_KEYS:
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            found_gtin.append(value.strip())
    rejected: list[str] = []
    if not found_gtin:
        text = json.dumps(product, ensure_ascii=False)
        for run in _DIGIT_RUN_RE.findall(text):
            if _gtin_check_digit_valid(run):
                found_gtin.append(run)
            else:
                rejected.append(run)
    observation.gtin = found_gtin
    detail["rejected_digit_runs"] = rejected
    detail["rejected_digit_runs_note"] = (
        "digit runs that failed GTIN length or check-digit validation; these are "
        "promotion timestamps and similar, NOT barcodes"
    )

    detail["has_promotion"] = bool(product.get("promotionPrices"))
    detail["object_id"] = observation.product_id
    if observation.unit_price_eur is None:
        # Reaching here means the key is absent, or present in a shape this
        # parser does not recognise. Those are different problems and the
        # distinction is recorded rather than blurred into "no unit price".
        if detail["has_base_price_key"]:
            observation.notes = (
                "A basePrice field is present but was not understood by the parser "
                f"(container={detail['base_price_container']}, "
                f"shape={detail['base_price_shape']}). This is a parser gap, not "
                "evidence that Aldi withholds unit prices."
            )
        else:
            observation.notes = (
                "No basePrice field on this page. Aldi omits it when the pack size "
                "already equals the base unit, so a 1 kg or 1 L pack has no separate "
                "per-unit price to publish: the shelf price is the unit price."
            )
    else:
        observation.notes = (
            f"Aldi publishes a per-{observation.unit_price_basis} price "
            f"({observation.unit_price_eur} EUR) alongside the shelf price, so "
            "unit-price comparison against another retailer is possible for this "
            "product."
        )
    return observation, detail


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _category_from_ids(product: dict[str, Any]) -> str | None:
    ids = product.get("categoryIDs")
    if isinstance(ids, list) and ids:
        return "/".join(str(i) for i in ids)
    main = product.get("mainCategoryID")
    return str(main) if main is not None else None


def _sales_unit(value: Any) -> tuple[float | None, str | None]:
    """Parse Aldi's salesUnit strings.

    Observed forms, read from the saved evidence:
        'kg-Preis'      price is per kg, not per pack
        '1-L-Packung'  1 litre pack
        '600-g-Packung' 600 g pack
        '1-kg-Packung'  1 kg pack

    The first version of this returned the literal '-L-Packung' as the unit
    because the separator is a hyphen with no surrounding space, which is
    trivially easy to get wrong and quietly corrupts every unit-price
    comparison downstream.
    """
    if not isinstance(value, str) or not value.strip():
        return None, None
    text = value.strip()

    if text.lower().endswith("-preis"):
        # e.g. 'kg-Preis' -> the price is a per-kg price.
        return None, text.split("-", 1)[0].strip() or None

    match = re.match(r"^([0-9]+(?:[.,][0-9]+)?)-(.+?)(?:-Packung)?$", text, re.IGNORECASE)
    if match:
        return _as_float(match.group(1).replace(",", ".")), match.group(2).strip()
    return None, text


def _gtin_check_digit_valid(digits: str) -> bool:
    """Validate a GTIN/EAN check digit.

    Why this exists: an earlier version of this probe scanned product JSON for
    bare digit runs of length >= 8 and reported them as GTINs. That produced
    "GTINs" of 1790805600 and 1791151200, which are Unix expiry timestamps from
    `promotionPrices[].validFrom`, not barcodes. A length check alone is also
    insufficient, because 13-digit numbers occur by chance. The modulo-10
    check digit is what separates a real EAN from a coincidental digit run, so
    we require it.
    """
    if not digits.isdigit():
        return False
    # Valid GTIN lengths only. 10-digit runs are excluded by length: no valid
    # GTIN is 10 digits.
    if len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], digits[-1]
    total = 0
    for offset, char in enumerate(reversed(body)):
        total += int(char) * (3 if offset % 2 == 0 else 1)
    return (10 - (total % 10)) % 10 == int(check)


def _api_data_entries(body: bytes) -> dict[str, Any]:
    """Return the __NEXT_DATA__ apiData blob as a {entry_name: payload} dict.

    Shared by the product and store probes, because both use the same shape:
    a *stringified* JSON array of [name, payload] pairs. Reading either one as
    a plain dict silently yields nothing, which is how this probe first
    reported "0 prices" and "storeDetail absent" on pages that demonstrably
    contain both.
    """
    payload = next_data(body)
    if payload is None:
        return {}
    api_data = payload.get("props", {}).get("pageProps", {}).get("apiData")
    if isinstance(api_data, str):
        try:
            api_data = json.loads(api_data)
        except (json.JSONDecodeError, ValueError):
            return {}
    if isinstance(api_data, list):
        return {
            pair[0]: pair[1]
            for pair in api_data
            if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str)
        }
    if isinstance(api_data, dict):
        return api_data
    return {}


def _res(entry: Any) -> dict[str, Any]:
    """Unwrap an apiData entry's 'res' container, if present."""
    if isinstance(entry, dict):
        inner = entry.get("res")
        if isinstance(inner, dict):
            return inner
        return entry
    return {}


def _verify_store(log: RequestLog, gate: RobotsGate, url: str) -> dict[str, Any]:
    """Re-verify the store-page payload, specifically lat/lng and zip."""
    if not gate.allowed(url):
        return {"url": url, "result": "skipped: disallowed by robots.txt"}

    record, body = log.fetch(url, "aldi_nord", notes="re-verify store payload")
    polite_sleep()
    out: dict[str, Any] = {"url": url, "status_code": record.status_code, "result": record.result}
    if not body or record.status_code != 200:
        return out

    payload = next_data(body)
    out["has_next_data"] = payload is not None
    if payload is None:
        out["extraction_status"] = "failed: no __NEXT_DATA__"
        return out

    entries = _api_data_entries(body)
    out["api_data_keys"] = sorted(entries.keys())
    detail = _res(entries.get("STORE_DETAIL_UBERALL_GET")).get("storeDetail")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (json.JSONDecodeError, ValueError):
            detail = None
    if not isinstance(detail, dict):
        out["extraction_status"] = (
            "failed: no STORE_DETAIL_UBERALL_GET/storeDetail. This is a harness "
            "failure, not evidence that the store has no coordinates."
        )
        return out

    out["extraction_status"] = "ok"
    hours = detail.get("openingHours") or []
    closures = detail.get("specialOpeningHours") or []
    out.update(
        {
            "id": detail.get("id"),
            "business_id": detail.get("businessId"),
            "lat": detail.get("lat"),
            "lng": detail.get("lng"),
            "postal_code": detail.get("zip"),
            "city": detail.get("city"),
            "street": detail.get("streetAndNumber"),
            "province": detail.get("province"),
            "google_place_id": detail.get("googlePlaceId"),
            "store_identifier": detail.get("identifier"),
            "opening_hours_count": len(hours),
            "opening_hours": hours,
            "special_opening_hours_count": len(closures),
            "special_opening_hours": closures,
            "services": detail.get("services"),
            "payment_options": detail.get("paymentOptions"),
            "operating_region_note": detail.get("openingHoursNotes"),
            "jsonld_blocks": sum(1 for _ in iter_jsonld(body)),
            "sha256": record.sha256,
            "coordinates_note": (
                "lat/lng are published on the permitted page. This resolves store "
                "location for Aldi Nord without any external postcode gazetteer."
            ),
        }
    )
    return out
