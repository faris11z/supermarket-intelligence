# 2026-09-30

## 08:56

Phase 1 data feasibility research. Pulled the full Open Prices dataset (318,731 observations across 7,414 stores) and joined it to the six target chains: Netto 3,776 obs / 2,402 products, EDEKA 2,384 / 1,612, REWE 1,669 / 1,331, Lidl 1,280 / 897, Aldi 1,211 / 852, Kaufland 1,021 / 931 - 11,341 observations total, only 3.6% of Open Prices. The blocking issue is cross-chain comparability: only 389 products (5.1%) are priced in 2+ chains and exactly 1 product is priced in all 6, because most items are chain-exclusive own-brand (Milbona, K-Classic, Milsani), so Open Prices alone cannot support six-way basket comparison. Idealo is the only rich multi-retailer German price source but exposes no public read API (partner/advertiser only), and offers, per-store availability and German review/sentiment data are either ToS-risky to scrape or absent from open feeds.

Reviewing the project requirements: the price engine, unit-price normalization and basket arithmetic are deterministic, while the only genuinely ML-justified parts are cross-chain product entity resolution and German sentiment/aspect classification. Analysis written up in `PROJECT.md` terms; repo is still docs-only (2 commits, no code, no dependencies installed).

### Things we do
- Read PROJECT.md / requirements.md and inspected the repository.
- Measured real coverage of Open Food Facts + Open Prices for all six chains (data downloaded to `/tmp/opencode/feasibility`, workspace untouched).
- Identified risks: data coverage, own-brand matching, availability gaps, review-data scarcity, scraping ToS.
- Proposed a re-ordered phased plan that validates data and picks a price-source strategy before any ML or app work.
- Flagged open decisions: accept scraping risk or stay strictly open-data; narrow to a subset of chains or keep all 6.

## 09:04

Supermarket data-acquisition spike. Made 39 HTTP requests total across the six chains (4 product-detail pages), with no headless browser, no JavaScript execution, and product discovery only via each site's own robots.txt-advertised sitemaps. Four chains are inaccessible to an ordinary client: aldi.de, edeka.de and netto-online.de return 403 from an Akamai edge, kaufland.de returns an explicit bot-verification challenge, and rewe.de serves robots.txt but answers all shop/product/sitemap paths with a 403 fallback shell containing no product markup. netto.de is fully crawlable but advertises zero product pages (560 URLs, all corporate). No CAPTCHA, UA spoofing, proxy rotation or post-block retry was used anywhere; every block was documented instead of worked around.

The one strong result is Aldi Nord, which publishes a robots-advertised catalog of 2,258 product URLs and serves complete prices in server-rendered HTML: current price, UVP reference price, €/kg unit price, promo label and explicit promotion validity dates, plus brand, sales unit, category taxonomy, availability, deposit and cold-chain flags. The key trap was Lidl, which has the cleanest integration in the spike (JSON-LD with GTIN-13 and even per-product aggregateRating) but whose catalog is wine, non-food and plants - substring searches for the whole test basket returned only false positives like Butterbirne, Eierlikör and Speierling, and zero real groceries. Aldi Nord also exposes no GTIN, so the only exact cross-chain join key is missing, which is what makes product matching the component most likely to genuinely need ML. Wrote `docs/research/supermarket-data-acquisition-spike.md` and saved the observed sample with provenance to `data/raw/spike/`.

### Things we do
- Read robots.txt for all six chains first and used it to gate every later request.
- Probed product discovery, product pages, price visibility, location dependency and structured data per chain.
- Extracted the Aldi Nord `__NEXT_DATA__` payload, discovering the price object is a *stringified* JSON blob that a naive parser silently misses.
- Verified Aldi Nord unit-price arithmetic (€6.79 / 600 g = €11.32/kg matches the observed base price).
- Classified every domain as accessible / partially blocked / blocked / no-catalog with the specific evidence.
- Documented the "no fabrication" boundary: absent fields stored as `null` with a note rather than filled in.
- Recorded recommendation Option B (feasible for some chains, not others) and the four cheap unknowns worth testing next, GTIN availability first.

## 09:18

Follow-up investigation on product matching, repeatability and the six-chain target. Three more requests (total 42) to test extraction stability: 3 additional Aldi Nord products (Weizenmehl, Bananen, Langkorn Reis) brought the sample to 5 pages across 4 categories, and all 5 parsed through the same code path. 19 core keys were present on every page, but 4 distinct optional-key schemas were observed, so brandName, promotionPrices, basePrice, legalInformation and meta fields all have to be treated as optional. Unit-price arithmetic verified exactly on 4 of 5 records (€2.49/0.750 kg = €3.32/kg, €6.79/0.600 kg = €11.32/kg, milk, and bananas which are sold by weight as "kg-Preis"), while Weizenmehl had no basePrice key at all and therefore must have its unit price computed rather than read. Established exhaustively that Aldi Nord exposes no GTIN: all 8-14 digit tokens scanned, gtin/ean/barcode keywords searched (3 hits per page, all false positives inside words like Clean/Cream/Mean), and all 24 product-object keys enumerated.

Re-checked robots.txt before making further requests and found /ua-bot.html and /mds/ are both disallowed despite /mds/ being the most likely place a GTIN would live, so neither was requested. A significant self-correction: an earlier analysis suggested ~78% of cross-chain Open Prices products had no name, which was an artifact of the prices export omitting product names that live in a separate products table. Re-measured on 30 randomly sampled cross-chain GTINs, 100% had name, brand and quantity and 97% had category, so name-based matching is viable, but only on the 388 of 7,559 DE products (5.1%) that appear in 2+ chains, and those names are messy and off-domain. Answers the five follow-up questions, recommends Option B, and redefines Phase 2 around making Aldi Nord a trustworthy one-chain reference implementation rather than a six-chain pipeline.

### Things we do
- Verified extraction robustness across product categories instead of trusting a 2-page sample.
- Retracted a wrong measurement rather than reporting it, and re-measured against the correct table.
- Distinguished "no GTIN on permitted pages" from "no GTIN on the site", since /mds/ is robots-disallowed and was left unprobed.
- Confirmed promo detection is reliable: strikePrice present on all 3 promoted products and absent on both unpromoted ones.
- Identified the by-weight edge case (kg-Preis) that will break any pack-size assumption.
- Set the honest ceiling: one usable chain now, six realistic only if the other five become reachable.

## 10:12

Phase 2 - location and travel feasibility. Reframed the project from "where is this basket
cheapest" to "given a postcode, a list and a transport mode, what is the cheapest way to buy
everything, and does a second store pay for itself". Wrote
`docs/research/location-and-travel-feasibility.md` and updated `PROJECT.md` to match. Bounded
research only: single geocoding lookups, two small bounding boxes, one-week price windows, no
bulk downloads, no spidering, and the same honest User-Agent as before. The most consequential
result is a silent-failure finding: the public OSRM demo server returns an identical
1,175 m / 165 s route for `driving`, `cycling` and `foot`, so it falls back to the car profile
instead of erroring. Trusting it would have overstated the appeal of distant stores for exactly
the pedestrians and cyclists for whom multi-store trips cost most, and it would have failed as
bad advice rather than as an error. Valhalla does differentiate the modes properly (auto
1.952 km/6.2 min, bicycle 1.149 km/4.4 min, pedestrian 0.980 km/11.6 min) but its public
instance has no transit data at all - `multimodal` fails with "Locations are in unconnected
regions" - so transit is a separate HAFAS/GTFS workstream. Transit data itself is reachable and
keyless via per-operator HAFAS wrappers (`v6.vbb.transport.rest` resolved Alexanderplatz stops;
the generic `v6.transport.rest` returned non-JSON). Postcode resolution is solved by a static
Apache-2.0 file with 8,298 centroid rows, and OpenPLZ covers the administrative hierarchy for
validation. OSM/Overpass carries enough branch data to be useful in cities (123 grocery features
in the Rostock box, 110 in Berlin, all six chains present; `addr:postcode` 75%, `website` 29%),
but a nationwide query returning 21,523 features is a count of OSM objects matching a name
filter, NOT a store count, and the main endpoint 504'd on it - so that number is explicitly
not quotable as "German stores".

Two findings reshaped the plan rather than just extending it. First, the Deutschlandticket is
€63/month from 01.01.2026 (verified against MVG, DB Regio MV, Wikipedia and tagesschau), so for
a holder the marginal cost of an extra transit leg is €0 and the optimal trip structure is
fundamentally different from a car user's - the answer is conditional on the user's transport
situation, and a single "best shop" answer would be wrong for a large share of users. Second,
and more uncomfortable: smhaggle already ships multi-store basket optimisation with
location-based store discovery ("buy everything from one retailer or visit several retailers"),
alongside incumbents kaufDA and Schlaukorb, whose own description is a list "automatically
sorted by market". The concept is therefore NOT novel, and the honest differentiator is much
narrower than the original brief: none of the verified competitors factor travel cost into the
recommendation, so the defensible claim is "cheapest total cost, including the trip". The
reassessment also shrank the honest ML surface - basket arithmetic, routing, store selection and
the travel/price trade-off are all deterministic and tractable exactly at 1-2 stores; only
cross-chain entity resolution and free-text list parsing genuinely need ML, and sentiment work
is deferred because there is still no review data to fit. Also noted that SMARD exposes
documented day-ahead wholesale prices (Q1 2026 average 102.17 €/MWh against a 656.37 €/MWh
record) but the `filter` parameter is a numeric module ID I did not resolve, its data licence is
unconfirmed, and a retail EV user is normally on a fixed tariff anyway - so that thread stays
open rather than becoming a feature.

### Things we do
- Verified postcode data rather than assuming it: Apache-2.0 licence confirmed, 8,298 rows, all five test PLZ present.
- Probed routing providers for mode support and found a silent car-fallback in the OSRM demo - a bug class worth more than the routing data itself.
- Established that transit routing, transit fares and transit data are three separate problems with three separate answers.
- Quantified the fixed/marginal split in transport cost, which is what makes the recommendation user-conditional.
- Searched the competitive landscape and found the core concept already shipped, rather than assuming novelty.
- Reduced, not expanded, the proposed ML scope, and gave a written reason for deferring sentiment.
- Graded every claim VERIFIED / PUBLISHED / INFERRED / ASSUMPTION / UNKNOWN, and recorded 8 open questions that block implementation.
- Corrected the stale spike metadata: `access_log.json` and `data/raw/spike/README.md` said 39 requests / 4 product pages, which became wrong after the 09:18 follow-up. A later edit over-corrected to "42 requests / 5 product pages (3 Aldi Nord, 2 Lidl)", conflating the Aldi-only count with the across-chain total. **Correct totals are now 53 requests / 7 product pages (5 Aldi Nord, 2 Lidl) plus 2 store pages**, and the 388-vs-389 cross-chain discrepancy stays flagged as unreconciled rather than quietly picked.

## 11:30

Lidl sitemap follow-up (8 requests, same honest UA, all to paths Lidl's own robots.txt
advertises). Two findings, one of which closes an open question and the other kills a
candidate data source.

**Lidl's store locator is solved.** Lidl advertises both a product sitemap and a store
sitemap from its robots-declared index. The store sitemap holds 3,669 URLs, but the real
find is that city index pages (`/s/de-DE/filialen/rostock/`) expose each store as an anchor
whose `aria-label` reads `Lidl Filiale {street}, {PLZ} {city}` - 10 Rostock stores extracted
with exact 5-digit postcodes, server-rendered, no JavaScript needed. No coordinates, no
opening hours, no schema.org, but the postcode alone joins to the `plz_geocoord` centroid
file, so this is a complete locator. Open question 1 goes from UNKNOWN to partly answered:
2 of 6 chains now have machine-readable stores, up from 0. Caveat recorded: the sitemap is
uneven, since `/filialen/berlin/` exists but has zero store-detail URLs, so city pages are
the reliable enumeration route rather than the sitemap.

**Lidl is simultaneously ruled out as a price source.** The 13,337-product catalog is ~99%
general merchandise and alcohol. Top own-brand families are esmara (clothing, 1,746),
livarno (furniture, 1,138), parkside (tools, 1,117), crivit (sportswear, 794), lupilu
(baby, 657) and silvercrest (kitchenware, 531) - about 55% non-food before alcohol. Two
product pages pinned the mechanism: a genuine grocery (Belbake Bio Dinkel-Mehl) returns
`"price":null`, no GTIN and `availability: InStoreOnly`, while a non-food storage box
returns 9.99 with two GTINs and `availability: OnlineOnly`. So Lidl publishes prices only
for its OnlineOnly range, and the real grocery range needs the store-selection flow, which
resolves through `/user-api/*` and `/cqe/*` - both robots-disallowed, so not probed. This
inverts the Phase 1 framing: Lidl was the "make-or-break for a second chain with GTIN", and
the answer is that the GTIN exists only where there is no grocery.

Also caught a classifier trap worth keeping: slug substrings lie.
`silvercrest-brot-frischhaltedose` contains `brot` but is a bread-freshness storage
container at 9.99, not bread. A slug-based grocery filter needs whole-token matching plus
human spot-checks, or it will silently classify kitchenware as food.

Evidence written to `data/raw/spike/lidl_catalog_and_stores.json` (factual fields, extraction
rule and sha256 digests rather than the 2.3 MB of copyrighted sitemap/page HTML, per the
existing convention), plus the 593-byte sitemap index in `robots_snapshot/`. Phase 2
report §2.2, §9 and Appendices A/B updated.

### Things we do
- Tested the single highest-value untested source and got a mixed verdict rather than a convenient one: better branch data, worse price data.
- Probed the robots-disallowed price endpoints' existence from the availability flag alone and stopped, instead of following them.
- Noted that a positive control matters: the non-food page with price+GTIN proves the extraction works, which is what makes the grocery null a real finding rather than a parse failure.
- Left open question 1 as partly answered with the remaining gap named (Aldi Nord postcodes) rather than marking it done.

## 11:52

Followed up on the open question the Lidl probe created, and answered it for Aldi Nord in
3 requests (11 total in this follow-up, now recorded in
`data/raw/spike/store_locator_findings.json`).

**Aldi Nord store pages are richer than Lidl's.** Aldi has no city index page -
`/filialen-und-oeffnungszeiten/rostock.html` is 404 and the bare city path only 308-redirects
to it - so unlike Lidl, enumeration must come from the store sitemap. But the individual
store page's `__NEXT_DATA__` → `props.pageProps.storeDetail` carries `lat` 54.16939 /
`lng` 12.083483, `zip` 18119 (the postcode the sitemap omits), seven `openingHours`
entries, dated `specialOpeningHours`, services, and payment options. Three things follow.

The coordinates are **real store positions, not postcode centroids** - cross-checked
against plz_geocoord, the Lortzingstraße store is 0.56 km from the 18119 centroid but
2.2-10.9 km from the other Rostock centroids compared against. Since a Rostock postcode
centroid can be several km from the actual shop, centroid placement would systematically
misfit walking distance. This is the strongest evidence yet for the total-cost framing,
because it is exactly the pedestrian/multi-store case the project is about.

`openingHoursNotes` names the operating **Regionalgesellschaft** (ALDI GmbH & Co. KG,
Jarmen), so each store identifies its own banner. That closes open question 2 for Aldi
Nord: banner-level assortment is derivable from the locator payload rather than needing a
separate source. A residual 2a is recorded - the entity is identifiable, but whether
assortment genuinely varies by region rather than only legally is untested.

Negative finding worth keeping: the page has 8 `application/ld+json` blocks but **none** is
a Store/LocalBusiness entity. Address and hours exist only in the Next.js payload, so a
generic "harvest schema.org" strategy would find nothing here.

Store locators are now solved for 2 of 6 chains with no external gazetteer, and open
questions 1 and 2 are answered for the chains that are reachable. Prices remain 1 of 6, and
the Lidl result reframes that risk: the barrier is data availability, not scraping
difficulty.

### Next
- The optimiser is not the bottleneck. Decide whether to accept a single-chain scope or spend more effort on a second price source (SMARD module ID remains the only unblocked lead).

