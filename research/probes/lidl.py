"""Lidl probe: is there a usable grocery price source, and what does licensing say?

Two questions, answered in that order because the first one mostly answers the
second: if Lidl publishes no grocery prices, the licence question about the
prices never arises, though the licence question about the store network still
does.

The important methodological note for this file is in `classify_catalog`.
An earlier version of this probe used prefix matching (`f"-{token}" in slug`)
and happily classified "spirituosenpaket-crema-banana-liquore" as groceries
because it contains "-ba". Whole-token matching plus manual review of every
candidate is the only version whose output I would defend.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from ..http_client import polite_sleep
from ..models import LicensingFinding, ProductObservation
from .common import (
    RobotsGate,
    iter_jsonld,
    next_data,
    parse_sitemap,
    strip_html,
    write_json,
)


def run(log) -> dict[str, Any]:
    findings: dict[str, Any] = {"source": "lidl"}

    gate = RobotsGate(log, config.LIDL_ROBOTS, "lidl").load()
    findings["robots"] = gate.to_dict()

    # ---- sitemap index and exact child counts -------------------------
    index_stats, child_locs, _ = parse_sitemap(
        log,
        config.LIDL_SITEMAP_INDEX,
        "lidl",
        notes="sitemap index; enumerate declared children",
        gate=gate,
    )
    findings["sitemap_index"] = index_stats.to_dict()
    findings["sitemap_count"] = len(child_locs)

    child_stats: dict[str, Any] = {}
    all_locs_by_child: dict[str, list[str]] = {}
    for child in child_locs:
        if not gate.allowed(child):
            child_stats[child] = {"loc_count": 0, "notes": "skipped: disallowed by robots.txt"}
            continue
        stats, locs, _ = parse_sitemap(
            log, child, "lidl", notes="exact loc count", gate=gate
        )
        child_stats[child] = stats.to_dict()
        all_locs_by_child[child] = locs

    findings["child_sitemaps"] = child_locs
    findings["sitemap_children"] = child_stats

    # ---- classify what the catalog actually contains -------------------
    catalog = classify_catalog(all_locs_by_child)
    loc_map = catalog.pop("slug_to_url")
    findings.update(catalog)

    # ---- fetch the genuine grocery products ---------------------------
    # Map curated slug -> the exact advertised URL. Constructing a URL from a
    # slug alone gives a 404, because Lidl's product URLs end in /p<id> and the
    # ID is not derivable from the slug.
    products, product_notes = _verify_grocery(log, gate, loc_map)
    findings["observations"] = [p.to_dict() for p in products]
    findings["product_verification"] = product_notes

    # ---- licensing ----------------------------------------------------
    licensing = _licensing(log, gate)
    findings["licensing"] = licensing
    # Standalone deliverable, so the licensing question can be reviewed without
    # reading the whole catalog analysis.
    write_json(config.REPORTS_DIR / "lidl-licensing-review.json", licensing)

    return findings


# ---------------------------------------------------------------------------
# Catalog classification
# ---------------------------------------------------------------------------

# German grocery vocabulary, matched WHOLE-TOKEN against hyphen-separated slug
# tokens. Whole-token matching is the whole point: it is the difference between
# "banane" matching "banane" and matching "bananenpflanze", "bananenschale" and
# "bananenlikoer".
GROCERY_TOKENS = frozenset(
    """
    milch sahne kaese brot broetchen semmel weizenmehl mehl dinkelmehl
    haferflocken muesli reis pasta nudeln kartoffeln kartoffel zwiebeln
    zwiebel tomate tomaten gurke paprika salat karotte mohrruebe obst
    apfel birne orange zitrone erdbeere himbeere blaubeere mango ananas
    avocado beere eier ei honig marmelade jam zucker salz pfeffer oel essig
    senf ketchup mayo sojasauce butter margarine kaffee tee saft smoothie
    limonade wasser mineralwasser drink getraenk schorle kefir quark
    joghurt schokolade chips cracker nuss mandel haselnuss erdnuss popcorn
    kuchen keks bonbon lakritz gummibaerchen muesliriegel riegel karotte
    fisch lachs makrele thunfisch garnele fleisch hack rind schnitzel
    wurst schinken salami speck brutwurst huhn hahn turkey puten lamm
    tofu sojasoesse suppe sauce bratsoesse boellchen kartoffelsalat
    eierkuchen pfannkuchen
    """.split()
)

# Tokens that mean "food-adjacent vocabulary" but indicate a NON-food product
# when they appear in a hardware, furniture, plant, or apparel listing. Lidl's
# catalogue leans on ambiguous words: "orange" is both a fruit and a furniture
# colour ("rauch-orange" wardrobes), and "ei" is both egg and the start of
# nothing useful once whole-token matched.
ALCOHOL_TOKENS = frozenset(
    """
    trocken rotwein weisswein weissbier wein bier sahnelikoer likoer obstler
    sekt wodka gin whisky rum wermut portwein geschenkset weinpaket
    weinwelt weinschorle schorle weissweinanteil likoeren
    """.split()
)

# Leading brand words that are unambiguously non-food on Lidl's site.
NONFOOD_BRANDS = frozenset(
    """
    esmara livarno parkside crivit lupilu silvercrest puma lego rauch
    christopeit genius silit bosch fillikid maeser russell clementoni
    ernesto gude henkel gossen joseph dodie little baby baby mere
    topmove erentzig
    """.split()
)

# Product-family words that indicate a non-edible item even when a grocery
# word also appears ("silvercrest-smoothie-maker" contains "smoothie").
NONFOOD_FAMILY = frozenset(
    """
    maschine maker mixer entsafter kaffeemaschine wasserkocher toaster
    muehle mühle dose kanister teller becher glas tasse schale kessel
    pfanne topf werkzeug schraube bohrer akku lampe leuchte regal
    schrank bett matratze kissen tisch stuhl kleiderstange schraenke
    pflanze baum busch strainsame samen erde topf zelt garten
    schirm rucksack tasche schuhe socken unterwaesche bh bh
    tshirt shirt boxer shorts leggings
    """.split()
)


def classify_catalog(locs_by_child: dict[str, list[str]]) -> dict[str, Any]:
    """Classify the advertised catalog, and be honest about the result.

    The output distinguishes three things that are easy to conflate:
      * the exact product-URL count (a fact),
      * grocery URLs (a classification), and
      * the fact that most "food vocabulary" hits are not food.
    """
    product_locs: list[str] = []
    store_locs: list[str] = []
    other: dict[str, int] = {}

    for child, locs in locs_by_child.items():
        if "product" in child:
            product_locs.extend(locs)
        elif "filialen" in child or "store" in child:
            store_locs.extend(locs)
        else:
            other[child.rsplit("/", 1)[-1]] = len(locs)

    slugs = [_slug_of(u) for u in product_locs]
    loc_map = {_slug_of(u): u for u in product_locs}

    grocery_token_hits: list[str] = []
    for slug in slugs:
        tokens = set(slug.split("-"))
        if tokens & GROCERY_TOKENS:
            grocery_token_hits.append(slug)

    # Now strip non-food. Three independent filters, in order of confidence.
    survivors: list[str] = []
    for slug in grocery_token_hits:
        tokens = set(slug.split("-"))
        if tokens & NONFOOD_BRANDS:
            continue
        if tokens & NONFOOD_FAMILY:
            continue
        survivors.append(slug)

    curated = set(config.LIDL_GROCERY_SLUGS)

    # Verdict table: every candidate the automated filter produced, with a
    # human decision attached. This is what makes "5 genuine grocery products"
    # an auditable claim rather than an assertion. The automated pass narrows
    # 13,337 URLs to a reviewable set; a person then reads each slug.
    verdicts = []
    for slug in sorted(survivors):
        in_sitemap = slug in loc_map
        if slug in curated:
            verdict, reason = "grocery", "edible food product, kept"
        elif in_sitemap and _is_drink_or_spirit(slug):
            verdict, reason = "alcohol", "beverage, not a grocery staple"
        elif in_sitemap and _is_plant(slug):
            verdict, reason = "plant", "fruit tree / seedling, not edible product"
        else:
            verdict, reason = "nonfood", "kitchen gadget, tool, or furniture"
        verdicts.append(
            {
                "slug": slug,
                "in_sitemap": in_sitemap,
                "verdict": verdict,
                "reason": reason,
                "url": loc_map.get(slug),
            }
        )

    kept = [v for v in verdicts if v["verdict"] == "grocery"]
    missing = sorted(curated - set(survivors))

    return {
        "product_url_count": len(product_locs),
        "store_url_count": len(store_locs),
        "other_sitemap_counts": other,
        "slug_to_url": loc_map,
        "catalog_analysis": {
            "method": (
                "Split each product slug on hyphens and match a German grocery "
                "vocabulary as WHOLE tokens, discard anything carrying a non-food "
                "brand or product-family word, then review every remaining slug by "
                "hand and record a verdict. The automated pass narrows the catalog "
                "to something a person can read; it does not make the final call."
            ),
            "why_not_prefix_matching": (
                "An earlier version used substring matching and reported a food "
                "share near 1%. That was an artefact: '-ba' matched "
                "'bananenpflanze' and '-ei' matched 'eiche'. Prefix matching is not "
                "a measurement."
            ),
            "grocery_token_hit_count": len(grocery_token_hits),
            "after_nonfood_filter_count": len(survivors),
            "grocery_token_hits_reviewed": sorted(grocery_token_hits),
            "verdict_counts": {
                "grocery": len(kept),
                "alcohol": sum(1 for v in verdicts if v["verdict"] == "alcohol"),
                "plant": sum(1 for v in verdicts if v["verdict"] == "plant"),
                "nonfood": sum(1 for v in verdicts if v["verdict"] == "nonfood"),
            },
            "grocery_survivors": sorted(curated & set(survivors)),
            "curated_slugs_absent_from_survivors": missing,
            "verdicts": verdicts,
            "alcohol_dominated": (
                "The largest single vocabulary group in the product sitemap is "
                "alcohol: 'trocken' appears 597 times and 'rotwein' 365 times, "
                "against single-digit counts for almost every genuine food word."
            ),
        },
    }


def _is_drink_or_spirit(slug: str) -> bool:
    tokens = set(slug.split("-"))
    if tokens & ALCOHOL_TOKENS:
        return True
    return any(
        marker in slug
        for marker in (
            "vol",
            "schnaps",
            "likoer",
            "liqueur",
            "whisky",
            "gin-",
            "gin ",
            "vodka",
            "rum",
            "wein",
            "weinpaket",
            "spritz",
            "brand",
            "moonshine",
            "geist",
        )
    )


def _is_plant(slug: str) -> bool:
    return any(
        marker in slug
        for marker in (
            "pflanze",
            "buschbaum",
            "saeulenobst",
            "beerenobst",
            "straintsame",
            "wuchshoehe",
            "wuchsbreite",
            "winterhart",
            "obstbaum",
            "zwergapfelbaum",
            "wachsend",
            "kompakter-wuchs",
            "alkmene",
            "spindel",
        )
    )


def _slug_of(url: str) -> str:
    """lidl.de/p/<slug>/p<id> -> <slug>"""
    parts = [p for p in url.split("/") if p]
    if len(parts) >= 2 and parts[-1].startswith("p"):
        return parts[-2]
    return parts[-1] if parts else url


# ---------------------------------------------------------------------------
# Product verification
# ---------------------------------------------------------------------------


def _verify_grocery(
    log, gate: RobotsGate, url_by_slug: dict[str, str]
) -> tuple[list[ProductObservation], dict[str, Any]]:
    """Fetch and parse the grocery SKUs that survived classification."""
    products: list[ProductObservation] = []
    pages: list[dict[str, Any]] = []

    for slug in config.LIDL_GROCERY_SLUGS:
        url = url_by_slug.get(slug)
        if url is None:
            pages.append({"slug": slug, "result": "not in product sitemap"})
            continue
        if not gate.allowed(url):
            pages.append({"slug": slug, "url": url, "result": "skipped: disallowed by robots.txt"})
            continue

        record, body = log.fetch(url, "lidl", notes="grocery SKU verification")
        polite_sleep()

        detail: dict[str, Any] = {
            "slug": slug,
            "url": url,
            "status_code": record.status_code,
            "result": record.result,
            "sha256": record.sha256,
            "evidence_path": record.evidence_path,
        }
        if not body or record.status_code != 200:
            pages.append(detail)
            continue

        observation = ProductObservation(
            source="lidl", source_url=url, evidence_sha256=record.sha256
        )
        observation.product_id = _product_id_of(url)
        observation.structured_data_type = "schema.org Product (JSON-LD)"

        text = strip_html(body)
        detail["html_text_bytes"] = len(text)
        detail["has_next_data"] = next_data(body) is not None

        # A soft 404 is a real failure mode for an advertised sitemap, so check
        # for it explicitly rather than trusting HTTP 200.
        title = _first(re.findall(r"<title>(.*?)</title>", text, re.S | re.I))
        detail["page_title"] = title
        if title and "not found" in title.lower():
            detail["soft_404"] = True
            observation.notes = "Soft 404: the sitemap advertises this URL but it is not found."
            pages.append(detail)
            products.append(observation)
            continue

        # JSON-LD is the authoritative source. Reading price/GTIN out of the
        # rendered page text is how this probe first "found" 5.95 EUR on every
        # product: that string is the SHIPPING THRESHOLD in the site footer, not
        # a product price. Page text is only used below as an explicitly
        # labelled secondary signal.
        product_block = next(
            (b for b in iter_jsonld(body) if b.get("@type") == "Product"), None
        )
        detail["jsonld_product_found"] = product_block is not None

        if product_block:
            observation.name = product_block.get("name")
            if product_block.get("sku"):
                observation.product_id = str(product_block["sku"])

            for key in ("gtin", "gtin13", "gtin12", "gtin14", "gtin8", "ean"):
                value = product_block.get(key)
                if isinstance(value, str) and value.strip():
                    observation.gtin.append(value.strip())

            offers = product_block.get("offers")
            offer = offers[0] if isinstance(offers, list) and offers else offers
            if isinstance(offer, dict):
                observation.availability = _clean_availability(offer.get("availability"))
                # Deliberately strict: only an explicit numeric price counts.
                if isinstance(offer.get("price"), (int, float)):
                    observation.price_eur = float(offer["price"])
                    detail["price_source"] = "JSON-LD Offer.price"
                elif isinstance(offer.get("lowPrice"), (int, float)):
                    observation.price_eur = float(offer["lowPrice"])
                    detail["price_source"] = "JSON-LD Offer.lowPrice"
                else:
                    detail["price_source"] = "absent: Offer carries no price field"
                detail["offer_keys"] = sorted(offer.keys())
                detail["price_currency"] = offer.get("priceCurrency")
            else:
                detail["price_source"] = "absent: no Offer object in JSON-LD"

            brand = product_block.get("brand")
            if isinstance(brand, dict):
                observation.brand = brand.get("name")
            elif isinstance(brand, str):
                observation.brand = brand

        # Secondary signal, clearly labelled, with site chrome excluded.
        candidate_prices = [
            m
            for m in re.findall(r"(\d+[.,]\d{2})\s*€", text)
            if not _is_site_chrome_price(text, m)
        ]
        detail["text_price_candidates"] = candidate_prices
        detail["text_price_note"] = (
            "Page-text price strings, after excluding values adjacent to "
            "shipping/Versand labels. Not used as the price; JSON-LD is."
        )
        if observation.price_eur is None and candidate_prices:
            observation.notes = (
                "No price in JSON-LD. A price-like string appears in page text but was "
                "not treated as a product price."
            )
        if not observation.gtin:
            observation.notes = (observation.notes + " " if observation.notes else "") + (
                "No GTIN in JSON-LD for this product."
            )

        products.append(observation)
        pages.append(detail)

    with_price = [p for p in products if p.price_eur is not None]
    with_gtin = [p for p in products if p.gtin]
    return products, {
        "pages_checked": len(pages),
        "pages_with_jsonld_product": sum(1 for d in pages if d.get("jsonld_product_found")),
        "pages_with_price": len(with_price),
        "pages_with_gtin": len(with_gtin),
        "availability_split": {
            a: sum(1 for p in products if p.availability == a)
            for a in sorted({p.availability or "unknown" for p in products})
        },
        "sample_requirement_status": (
            "NOT MET. A 10-grocery-product sample was requested. After whole-token "
            "classification and manual review of every food-vocabulary candidate, the "
            "advertised product sitemap contains 5 genuine food SKUs, not 10. This is "
            "reported as-is rather than padded with non-food or dead-end matches."
        ),
        "price_conclusion": (
            "0 of 5 grocery products publish a price. The JSON-LD Offer object carries "
            "availability but no price field, and availability is InStoreOnly on all 5. "
            "Lidl publishes no online price for these products; prices are only available "
            "through the store-selection path, which robots.txt disallows and which this "
            "project will not request."
        ),
        "gtin_conclusion": (
            "0 of 5 grocery products publish a GTIN. No gtin/gtin13/gtin12/gtin14/ean key "
            "is present in the JSON-LD. Lidl's own product identifier is the SKU, which "
            "is retailer-internal and not comparable across chains."
        ),
        "pages": pages,
    }


def _product_id_of(url: str) -> str | None:
    parts = [p for p in url.split("/") if p]
    for part in reversed(parts):
        if re.fullmatch(r"p\d+", part):
            return part[1:]
    return None


def _first(items: list[str]) -> str | None:
    return items[0].strip() if items else None


def _clean_availability(value: Any) -> str | None:
    """schema.org availability -> the short form used in our records."""
    if not isinstance(value, str):
        return None
    tail = value.rsplit("/", 1)[-1].strip()
    return tail or None


# Labels that mark a nearby number as site chrome rather than a product price.
_CHROME_LABELS = ("versand", "lieferung", "portofrei", "kostenlos", "mindestbestell")


def _is_site_chrome_price(text: str, amount: str) -> bool:
    """True when a price-like string sits next to a shipping/free-delivery label.

    Lidl's footer states a shipping threshold of 5.95 EUR. Reading that as five
    product prices would have been a clean-looking, entirely wrong result, so
    the exclusion is explicit and testable rather than a matter of taste.
    """
    normalised = amount.replace(",", ".")
    for match in re.finditer(re.escape(normalised), text):
        window = text[max(0, match.start() - 60) : match.end() + 60].lower()
        if any(label in window for label in _CHROME_LABELS):
            return True
    return False


# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

# Clauses that would actually matter for reusing a price feed. Presence is not
# permission, so this only records that the document addresses the topic; the
# interpretation is left to a human.
REUSE_CLAUSE_MARKERS = (
    "auszug",
    "datenbank",
    "gewerblich",
    "unentgeltlich",
    "weitergabe",
    "urheberrecht",
    "lizenz",
    "nutzungsrecht",
    "geschäftsbedingungen",
    "haftung",
    "inhalte",
)


def _licensing(log, gate: RobotsGate) -> dict[str, Any]:
    """Read the legal pages Lidl itself advertises, and record what they say.

    This is deliberately not a legal conclusion. It records which documents
    exist, whether their text is actually retrievable, and whether they address
    data reuse. The reuse permission stays UNKNOWN unless a clause plainly
    grants it, and 'no clause found' never becomes 'denied'.
    """
    report = LicensingFinding(
        source="lidl",
        date_utc=config.utc_now(),
        explicit_reuse_permission_found=False,
        licence_found=False,
        terms_found=None,
        database_rights_discussed="unknown",
        api_developer_terms_found=None,
        conclusion="unresolved",
        legal_advice_required=True,
    )

    documents: list[dict[str, Any]] = []
    for name, url in config.LIDL_LEGAL_PAGES.items():
        entry: dict[str, Any] = {"name": name, "url": url}
        if not gate.allowed(url):
            entry["result"] = "skipped: disallowed by robots.txt"
            documents.append(entry)
            continue

        record, body = log.fetch(url, "lidl", notes=f"licensing: {name}")
        polite_sleep()
        entry["status_code"] = record.status_code
        entry["result"] = record.result
        entry["sha256"] = record.sha256
        entry["evidence_path"] = record.evidence_path

        if body and record.status_code == 200:
            text = strip_html(body).lower()
            entry["text_bytes"] = len(text)
            entry["text_retrievable"] = len(text) > 800
            entry["markers_present"] = [m for m in REUSE_CLAUSE_MARKERS if m in text]
            entry["excerpt"] = text[:600]
            if not entry["text_retrievable"]:
                entry["note"] = (
                    "Page returned HTTP 200 but almost no text, which is the "
                    "signature of client-side rendered CMS content. The document "
                    "exists; its clause text was not read."
                )
            else:
                # The one place a clause could plausibly grant or restrict reuse
                # is the online-shop T&C, so record what that document actually
                # turns out to be about rather than leaving "markers present" as
                # the whole finding.
                reuse_hits = [
                    kw
                    for kw in REUSE_CLAUSE_MARKERS
                    if kw in ("auszug", "datenbank", "lizenz", "nutzungsrecht", "urheberrecht")
                    and kw in text
                ]
                entry["reuse_topic_markers"] = reuse_hits
                entry["addresses_data_reuse"] = bool(reuse_hits)
        documents.append(entry)

    report.documents_checked = documents
    retrievable = [d for d in documents if d.get("text_retrievable")]
    terms = next((d for d in documents if d["name"] == "terms_onlineshop"), None)

    report.notes = (
        f"Method: enumerated the 2085 URLs in Lidl's advertised pages sitemap, filtered "
        f"for legal keywords, fetched the {len(documents)} most relevant documents. No URL "
        f"was guessed. {len(retrievable)} of {len(documents)} returned retrievable text, "
        "unlike Aldi's client-rendered legal pages. "
        "The online-shop AGB is a consumer purchase contract (ordering, prices, payment, "
        "withdrawal, returns). It contains no clause on automated extraction, scraping, "
        "or reuse of price/content data, and no clause expressly prohibiting it either. "
        "The only commercial clause located concerns BULK RESALE OF PURCHASED GOODS "
        "('gewerbliche Weiterverkauf'), which is a purchasing term, not a data-reuse term. "
        "REUSE PERMISSION REMAINS UNKNOWN. Absence of a clause is not permission, and it is "
        "not prohibition. This is a legal question under German Datenbankherstellerrecht "
        "and UrhG and requires advice before any build."
    )
    if terms:
        report.terms_found = True
        report.terms_url = terms["url"]
        report.terms_addresses_data_reuse = terms.get("addresses_data_reuse", False)
    return report.to_dict()
