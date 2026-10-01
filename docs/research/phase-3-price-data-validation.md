# Phase 3: price data and licensing validation

Date: 2026-09-30
Scope: reproduce the price-source findings with auditable code and saved
evidence, test open-data fallbacks for real, and settle what is licensed enough
to build on.

**Verdict: not ready for a real-time multi-chain price comparison.** Live price
coverage is 1 of 6 target chains, no retailer publishes a GTIN on permitted
pages, and reuse permission is unresolved for both retailers that do respond.

## How to check any claim in this report

```bash
python -m research.run_probe --list     # what can be probed
python -m research.run_probe            # re-run, bounded and logged
python -m research.run_probe --offline   # re-derive from saved evidence, no network
python research/verify_phase3.py         # 26 offline consistency checks
python research/check_docs_consistency.py # catch stale numbers in the docs
```

`verify_phase3.py` re-parses the saved responses rather than trusting these
reports, so if a report drifts away from its evidence the check fails. All 28
checks currently pass. That means the **evidence is self-consistent**. It does
not mean the sources are usable or licensed; those are the decision gate below.

### How many requests were actually made

**117 real GET requests, across 53 distinct URLs.** That is the number to quote.

`data/research/request_log.jsonl` currently holds 349 records, which is a
different and much larger number, and the reason matters:

| Log content | Count | What it is |
|---|---|---|
| real GET requests | 117 | requests this project actually sent to a server |
| offline replay records | 218 | `run_probe --offline` re-reading saved evidence |
| evidence tombstones | 14 | deliberate local deletions, not requests |
| **total lines** | **349** | |

**Correction.** This report previously said "235 GET requests were made across 53
distinct URLs", and `README.md`, `research/README.md` and `timeline.md` repeated
it. That number was wrong. `run_probe --offline` appends one log line per URL it
replays, and at the time the sentence was written the file held 117 real requests
plus 118 replay lines. The replay lines were counted as requests made. The 53
distinct URLs was correct; the 235 was not. The same paragraph also described the
log as holding 242 records when it held 280.

The harness now writes an explicit `replayed: true` flag on every replay line, so
this cannot recur by accident. Replay lines are also excluded from the count
above. Note that the 218 replay figure grows every time someone re-runs the
offline probe; the 117 does not, because offline runs make no network requests.

Every real request is in `data/research/request_log.jsonl` with status, bytes,
redirect chain and SHA-256. The per-run cap is 120
(`config.MAX_REQUESTS_PER_RUN`) and no run approached it. The repeated URLs are
re-fetching the same sitemaps while parsers were being corrected, not breadth of
crawling.

## Findings

### 1. Aldi Nord: prices yes, barcodes no, and per-unit prices after a parser fix

Exact counts from the advertised sitemap index (4 children):

| Sitemap | `<loc>` count |
|---|---|
| stores | **2,236** |
| products | 2,258 |
| pages | 649 |
| faq | 7 |

**Correction to a previous finding.** The store count of ~1,693 was inferred
from store ID ranges. It was never a measurement. The exact count is 2,236,
which is 543 higher. The estimate is superseded, not adjusted.

Re-checking the five previously sampled product pages, 4 of 5 parsed:

| Product | Price | Unit | Promotion |
|---|---|---|---|
| Frische Milch (Bärenmarke) | 0.99 | 1 L | was 1.59 (UVP) |
| Hähnchenbrustfilet-Teilstücke | 6.79 | 600 g | none |
| Weizenmehl (Back Family) | 0.59 | 1 kg | none |
| Bananen | 0.99 | per kg | was 1.29 |
| Langkorn-Reis | extraction failed | | |

The fifth page redirects to a variant that renders without the product payload.
That is recorded as an extraction failure, not as a product without a price.

**Prices: 4 of 4 parsed pages. GTIN: 0 of 4.**

**Aldi does publish per-unit prices, and Phase 3 initially reported that it
did not.** This is the most consequential correction in the report, so it is
recorded in full.

| Product | Shelf price | Aldi's published basePrice | Scale |
|---|---|---|---|
| Frische Milch (Bärenmarke) | 0.99 | **0.99** | per L |
| Hähnchenbrustfilet-Teilstücke | 6.79 | **11.32** | per kg |
| Bananen | 0.99 | **0.99** | per kg |
| Weizenmehl (Back Family) | 0.59 | none published | 1 kg pack |

The field is an array of objects nested *inside* `currentPrice`, as a sibling of
`priceValue`:

```json
"currentPrice": {"priceValue": 6.79,
                 "basePrice": [{"basePriceValue": 11.32, "basePriceScale": "kg"}]}
```

The parser read `product['basePrice']` and `product['basePriceUnit']`, both one
level too shallow, and both returned `None`. Its diagnostic
`has_base_price_key = 'basePrice' in product` was `False` for the same reason.
The report therefore stated "no basePrice field" while the value sat in the very
dict the parser had already read a shelf price from. Only the archived HTML
exposed it: 3 of the 5 sampled pages contain `basePrice` (6, 6 and 3
occurrences), and those values match Phase 1's recorded figures exactly.

Phase 1 was right. The lesson is recorded because the failure mode is
dangerous rather than merely wrong: a parser that returns `None` for a field it
mis-reads is indistinguishable from a retailer that does not publish that
field. A false negative about a data source is far more costly than a missing
feature, because it removes a source from consideration on false grounds. The
verifier now re-derives `basePrice` from the raw bytes and fails if the parser
and the archive disagree, and the parser records which shape it found
(`base_price_container`, `base_price_shape`) so a future shape change is visible
instead of silently reverting to "Aldi does not publish unit prices".

Weizenmehl genuinely has no `basePrice`, and that is not a miss: it is a single
1 kg pack, so the shelf price is already the unit price and there is nothing
extra to publish. The verifier requires this explanation to hold rather than
accepting an unexplained absence. The fifth product, Langkorn-Reis, rendered an
empty shell and supports no conclusion in either direction.

Consequence for the project: **unit-price comparison against another retailer is
possible for Aldi products**, which the previous version of this report said it
was not. The GTIN gap is unaffected, so matching a competitor's identical product
to Aldi's product is still not possible. Comparing two retailers requires
matching by name, which is the fragile approach flagged below.

### 2. Lidl: no grocery prices, and the catalog is not a grocery catalog

The advertised product sitemap holds 13,337 URLs. Whole-token classification of
the slugs plus a hand review of every surviving candidate gives:

| Verdict | Count |
|---|---|
| genuine food | **5** |
| alcohol | 24 |
| plants and seedlings | 12 |
| non-food gadgets and furniture | 7 |

The five food SKUs are Belbake spelt flour (2), Crownfield muesli (2) and
Grafschafter brunch rolls. Lidl's grocery own brands (Solevita, Vitafit, Hahne,
Oberland, Fresko) appear **zero** times in the catalog. The largest vocabulary
group is alcohol: `trocken` 597 times, `rotwein` 365.

All five food pages return valid schema.org `Product` JSON-LD with an `Offer`
that carries `availability: InStoreOnly` and **no price field**, and **no
GTIN**. Lidl publishes no online price for these products. The only prices sit
behind the store-selection path, which `robots.txt` disallows, so we do not
request it.

**A requested deliverable could not be met.** The brief asked for a
deterministic sample of 10 ordinary grocery products. The advertised sitemap
contains 5. This is reported as unmet rather than padded with alcohol, seedlings
or dead links, and `verify_phase3.py` has a check that fails if this is ever
quietly redefined as a success.

An earlier phase estimated "roughly 1% grocery" using substring matching on
slugs. That number was an artifact: `-ba` matched `bananenpflanze` and `-ei`
matched `eiche`. It is withdrawn. The measured answer is 5.

### 3. Licensing: unresolved for both, and that is the real blocker

**Lidl.** Its advertised pages sitemap (2,085 URLs) contains the legal
documents, so nothing had to be guessed. Five were fetched and all five returned
readable text:

| Document | URL |
|---|---|
| Online-shop terms (AGB) | `lidl.de/c/allgemeine-geschaeftsbedingungen-onlineshop/s10005181` |
| Impressum | `lidl.de/c/impressum/s10005238` |
| Legal information | `lidl.de/c/rechtliche-informationen/s10005200` |
| Privacy | `lidl.de/c/datenschutz/s10005389` |
| Withdrawal rights | `lidl.de/c/widerrufsrecht-onlineshop/s10005170` |

The AGB is 27.7 KB of consumer purchase terms: ordering, prices, payment,
withdrawal, returns. It contains **no clause on automated extraction,
scraping, or reuse of price and content data**, and no clause expressly
prohibiting it either. The only commercial clause located concerns bulk resale
of *purchased goods* (`gewerbliche Weiterverkauf`), which is a purchasing term,
not a data-reuse term.

**Aldi.** The 649-URL pages sitemap exposes 5 privacy pages and 7
promotion-terms pages, but no general terms of use and no Impressum with a reuse
permission. Those pages are client-rendered, so their clause text was not
readable and no further URL guessing was attempted.

**Conclusion: UNKNOWN, not denied.** No explicit reuse permission was found, and
no prohibition was found either. Absence of a clause is neither permission nor
refusal. This is a legal question under `Datenbankherstellerrecht` and `UrhG`
and it cannot be answered by more HTTP requests.

### 4. Open data: all six tested, none closes the gap

| Source | Result | What it actually gives |
|---|---|---|
| Open Food Facts | PASS | product records, GTIN as primary key, **no prices** |
| Open Prices | PASS, **318,982** observations | historical crowdsourced prices, CC BY-SA reported |
| OpenStreetMap | PASS but flaky | store nodes; public mirrors return 504s and time out |
| plz_geocoord | PASS, 8,298 rows | postcode centroids, Apache-2.0 verified from source |
| Nominatim | PASS | address geocoding, 1 req/s policy |
| SMARD | PASS | wholesale electricity and gas, **wrong domain** |

The Open Prices live total of 318,982 is consistent with the 318,731 measured in
Phase 1; the dataset has simply grown. Its licence is the most permissive thing
we found. It still cannot be a live price source, and Phase 1 already showed
only ~5.1% of German products appear in two or more chains.

**A methodological trap worth recording:** `prices.openfoodfacts.org` returns
HTTP 200 with a Vue single-page-app HTML shell for any non-API path. A
status-code-only health check would report the API as working while returning
26 KB of HTML. The probe requires a JSON parse before it will call the endpoint
reachable. It initially reported the API as unreachable for the same reason in
reverse: the correct path was dismissed as a shell.

## The structural problem

Three sources, none of which joins to the others:

- Aldi publishes **prices** and its own **per-unit prices**, but no **barcodes**.
- Lidl publishes **neither prices nor barcodes** on the five grocery pages that
  exist. Its internal `p10079984` SKU is not a barcode, so it does not help.
  (Phase 1 believed Lidl exposed GTIN-13; that claim came from a *wine* page and
  is corrected in the acquisition spike doc.)
- Open Prices publishes **barcodes** with **historical** prices.

Cross-chain product identity needs a barcode from the retailer. None of the six
target chains provides one on a permitted page. So the blocker is not "we need
more price data", it is "we cannot prove two records are the same product". A
fuzzy name match on 5% of products, with category filtering, would produce
confidently wrong prices, which is worse than shipping nothing.

## Claims in this project that have no stored evidence

Everything above is backed by a file in `data/research/` that the verifier can
re-read. The claims below are **not**. They are beliefs recorded in prose during
earlier phases, and no archived response or measurement in this repository
supports them. They are listed so that nobody later mistakes them for findings.

| Claim | Where it appears | Status |
|---|---|---|
| "GTIN-13 barcodes present" on Lidl | acquisition spike, §"single most important finding" | **Wrong** — measured 0 of 5 grocery pages. The Phase 1 observation was on a wine page. |
| Per-product `aggregateRating` (4.5 stars, 54 reviews) | acquisition spike | **Wrong for groceries** — observed on a wine page; absent from the 5 grocery pages. |
| "Contains no ... flour" in Lidl's catalog | acquisition spike | **Wrong** — `belbake-dinkelmehl-vollkorn` and the Bioland variant are in the sitemap. |
| Aldi's 2,258-product sitemap is current | acquisition spike | Unverified. Counted once; no re-check, and product ranges churn. |
| Lidl catalog is "~99% non-food and alcohol" by own-brand family counts | `data/raw/spike/access_log.json` | **Superseded.** The family counts (esmara 1746, livarno 1138, ...) were not re-derived in Phase 3. Phase 3's whole-token review of 48 survivors gives 24 alcohol / 12 plants / 7 non-food / 5 grocery. Both are consistent in direction; only Phase 3's is measured on all candidates. |
| Netto's 560 sitemap URLs contain zero product pages | `access_log.json`, location doc | Unverified in Phase 3. Netto was not re-probed. |
| Kaufland / EDEKA / REWE / Aldi-Süd are edge-blocked | `access_log.json`, all docs | Unverified in Phase 3. Not re-probed, deliberately: re-probing a block to confirm it still blocks drifts toward circumvention. |
| Competitor apps "treat product as basket" | acquisition spike, competitor research | **Prose only.** No competitor was re-examined in Phase 3 and no citation is stored. |
| Human physical effort / carrying cost is not modelled | not stated anywhere in the repo | **True and unstated.** There is no energy or effort model for the human. Only vehicle fuel and EV electricity are costed. This is a gap, not a finding. |
| SMARD data is CC BY 4.0 | location doc §4.2 | **Explicitly UNKNOWN in the same document.** Secondary sources only; never verified against SMARD's own terms. |
| Deutschlandticket and fuel/EV cost figures | location doc | Sourced from web research in Phase 2 with no archived copy of the source pages. Re-verify before using any number commercially. |

The last row is the general problem: Phase 2 did web research whose pages were
not archived, so those numbers cannot be re-checked offline today. That is why
`verify_phase3.py` makes no claim about them.

## Decision gate

**Not ready.** Three blockers, in order:

1. Only 1 of 6 chains publishes a price on permitted pages.
2. No retailer publishes a GTIN, so cross-chain matching cannot be exact.
3. Reuse permission is unresolved for both responsive retailers, and further
   technical probing cannot resolve it.

**Viable right now, with no unresolved legal question:**

- Store location and opening hours. Aldi publishes coordinates; Lidl city pages
  give postcode-level store lists.
- Travel-time modelling and total-cost arithmetic. This is the defensible
  differentiator: the competitor research found existing basket optimisers
  already treat "product" as "basket", so travel cost plus transport-mode
  selection is the gap.
- Open Prices as licence-clean, coverage-thin historical reference data.

**Needs a human decision, not more research:**

- Obtain legal advice on `Datenbankherstellerrecht` and `UrhG`, or written
  permission from the retailers.
- Decide whether the product is viable with one live price source plus
  crowdsourced or manual prices, or whether it needs a commercial data partner.
  This is a product and business decision, not a technical one.

## What this harness refuses to do

No retry logic, no proxy support, no cookie jar, no credential handling, no
JavaScript rendering, no URL guessing, and no crawling of disallowed paths. A
403 is recorded and the path is dropped. `robots.txt` permission is treated as
a hard gate and is explicitly **not** treated as a licence.

Deliberately absent, and each would change the ethics of the project: adding a
retry parameter, adding a proxy option, adding a headless browser. Rendering
client-side pages is the step that turns a polite research client into
something that looks like an attack, and the licence question sits downstream of
it.

## Artifacts

| Path | What it is |
|---|---|
| `research/` | the harness; `README.md` explains the design and the refusals |
| `data/research/request_log.jsonl` | append-only, one JSON object per request. Currently 349 records = 117 real GETs + 218 replays + 14 evidence tombstones. The log grows every offline run; the 117 does not. |
| `data/research/raw/` | saved response bodies, content-addressed by SHA-256 |
| `data/research/normalized/` | comparable product records per source |
| `data/research/reports/aldi.json` | counts, prices, store payload, licensing |
| `data/research/reports/lidl.json` | catalog verdicts, product payloads, licensing |
| `data/research/reports/lidl-licensing-review.json` | standalone licensing review |
| `data/research/reports/alternatives.json` | six open sources, actually tested |
| `docs/research/source-suitability-matrix.md` | the decision table |

## Known limitations of this phase

- Four of six chains were not re-probed in Phase 3. They were ruled out in
  Phase 1/2 and re-probing them would not change the verdict.
- The Lidl catalog classification is a hand review of 48 candidates, encoded as
  an allowlist in `config.LIDL_GROCERY_SLUGS`. It is deterministic and
  auditable, but it is a judgement, and a different reader could classify one or
  two borderline slugs differently. The review table is in the report so that
  judgement can be checked.
- Open Prices and Open Food Facts licence claims are carried from Phase 1 and
  were not re-verified from primary sources, because the licence pages could not
  be located without guessing URLs. They are marked unverified in the matrix.
- Aldi's `InStoreOnly` products and Lidl's lack of online prices may be
  regional or seasonal. Five Lidl products with adjacent IDs suggests a small
  recent batch, and a larger sample at a different time of year could differ.
- The 0.563 km postcode-centroid error is one measurement in one postcode, not
  a distribution.
