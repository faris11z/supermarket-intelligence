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


## 12:40

Data-licensing review, 14 requests, all to robots-permitted paths on aldi-nord.de. Done
because this could invalidate every technical finding so far, and it was the cheapest open
question to test. It could not be resolved, and the failure mode turned out to be the
interesting part.

Aldi Nord's pages sitemap holds 649 URLs, of which 5 are GDPR/privacy pages and 7 are
promotion or lottery terms (Gewinnspiele, E-Ladesaeulen, social channels, Bollerwagen).
There is **no general Terms of Use and no Impressum** anywhere in the sitemap, so there is
no published document granting reuse and none in which to seek permission. Guessing paths
produced three 404s; the homepage server-renders only 6 href elements, none of them legal,
because the footer is client-rendered.

The decisive detail is that the legal text is not retrievable without executing JavaScript.
The Datenschutz page server-renders **36 characters** of body text. The
teilnahmebedingungen-agb page has `apiData: null` in `__NEXT_DATA__` and fetches its content
from a CMS on the client. So even if a relevant clause existed, we could not read it under
this phase's declared method.

The reasoning that matters: **absence of a published prohibition is not permission.** Under
UrhG §87b a database maker who made a substantial investment holds an exclusive right to
reproduce and redistribute substantial parts of it, which is exactly what a retailer product
catalog is. With nothing granted, the default is all-rights-reserved. And robots.txt is a
crawl instruction, not a licence. That distinction is easy to conflate and expensive to get
wrong, so it is now written into §2.4 of the Phase 2 report and raised to open question 9
as the highest-priority blocker.

The recommendation is deliberately to stop fetching. More requests cannot answer this,
because the answer is not on the website. It needs a lawyer. Until then the defensible
position is: prototype on the observations already cached in this repo, no redistribution,
no production ingestion pipeline, and cite sources rather than mirror catalogs.

One assumption is flagged rather than hidden: that personal, non-commercial research on a
handful of pages is tolerated. Probably true, and Aldi does publish a permissive robots.txt,
but tolerated is not licensed, and this project intends to be a product.

Also logged 14 requests properly, so `access_log.json` now totals 67 and carries a
per-request `legal_review_requests` list, including the 7 redirected-and-discarded URL
probes. The log staying honest matters more than the request looking tidy.

### Things we do
- Chose the cheapest question that could invalidate the project, and tested it before writing any pipeline.
- Reported "unresolved" instead of assuming the permissive robots.txt meant permission.
- Separated "we could not read the terms" from "there are no terms", which are different failures with different fixes.
- Flagged an assumption about tolerated research use rather than letting it harden into practice.

---

## Phase 3

Started because Phases 1 and 2 established what *might* be available, but every
number in them was hand-copied out of HTML. Nothing was re-derivable, and three
of the estimates turned out to be wrong. So the question was not "what can we
get", it was "can we prove it, and would it survive being checked".

Built a small harness instead of a pipeline: one probe per source, one GET per
URL, no retries, no proxy, no cookie jar, no JavaScript rendering, and every
request appended to `data/research/request_log.jsonl` with its SHA-256 and saved
response body. `research/verify_phase3.py` re-parses those saved bodies rather
than trusting the reports, so a report that drifts from its evidence fails the
check. 28 checks, all passing, which means the evidence is self-consistent. It
does not mean the sources are usable, and the harness says so in its own output.

### The store count was never measured

Phase 2 reported roughly 1,693 Aldi Nord stores. That number was inferred from
store ID ranges, and inference is not measurement. The advertised sitemap index
gives **2,236** exactly, 543 more than estimated. The estimate is now marked
superseded rather than quietly adjusted, because a number that was never
measured should not be allowed to drift into looking like one.

### "Roughly 1% grocery" was an artifact of substring matching

Phase 2 estimated Lidl's catalog was about 1% food, using substring matching on
URL slugs. Phase 3's whole-token match plus a hand review of every survivor
finds the advertised catalog is 13,337 URLs of which **5** are genuine food. The
old estimate overcounted because `-ba` matched `bananenpflanze` and `-ei` matched
`eiche`. Withdrawn.

The same 48 candidates that survived filtering, read by hand: 24 alcohol, 12
plants and seedlings, 7 non-food, 5 food. The largest group is alcohol, and
Lidl's actual grocery own brands appear zero times in the catalog.

### A deliverable was requested that the data does not support

The brief asked for a deterministic sample of 10 ordinary grocery products from
Lidl. The advertised sitemap contains 5. Reported as unmet rather than padded
with alcohol, seedlings, or dead links, and the verifier now fails if that is
ever quietly redefined as a success. This is the kind of gap that is easiest to
paper over and most expensive to ship.

### Lidl's prices are not behind a bot wall, they are simply absent

All five food pages return valid `Product` JSON-LD whose `Offer` carries
`availability: InStoreOnly` and **no price field**, and no GTIN. Lidl publishes
no online price for these products at all. The only prices sit behind the
store-selection path, which robots.txt disallows, so we do not request it. The
finding is stronger than "blocked": there is nothing there to block.

### The licensing question was half-closable, and the half that closed is not permission

Phase 2 could not read Aldi's legal pages because they are client-rendered.
Lidl's pages sitemap, however, lists its own legal documents, so Phase 3
retrieved all five and they render server-side. The Online-shop AGB is 27.7 KB
of consumer purchase terms: ordering, payment, returns, withdrawal. It contains
no clause on automated extraction, scraping, or reuse, and no clause
prohibiting them either. The only commercial clause found concerns bulk resale
of purchased goods, which is a purchasing term, not a data-reuse term.

So the honest status is **unknown, not denied**, for both retailers. Absence of a
clause is neither permission nor refusal, and Phase 2's reasoning holds: the
answer is not on the website, it needs a lawyer. We stopped fetching, because
more requests cannot answer it.

### The actual blocker is product identity, not price data

Worth separating, because the whole project was pointed at the wrong target for
two phases. The sources do not join to each other:

- Aldi publishes **prices** but no **barcodes**.
- Lidl publishes a **SKU** but no **prices**.
- Open Prices publishes **barcodes** with **historical** prices.

Cross-chain matching needs a barcode from the retailer, and none of the six
target chains publishes one on a permitted page. So a price comparison across
chains cannot be made exact. Fuzzy name matching on ~5% of products would
produce confidently wrong prices, which is worse than shipping nothing. No amount
of additional price sourcing fixes this, which is why the phase ended with a
recommendation to stop looking for a public price feed rather than keep hunting.

### A 200 that means nothing

`prices.openfoodfacts.org` returns HTTP 200 with a Vue single-page-app HTML
shell for any non-API path. A status-code health check would call the API
working while handing back 26 KB of HTML. The probe now requires a JSON parse
before it will call an endpoint reachable. It also initially reported the API
as *unreachable*, for the mirror-image mistake of dismissing the real endpoint
as a shell. The live total is 318,982 against Phase 1's 318,731, so the dataset
simply grew. The API works; its coverage is still too thin to help, which is
what Phase 1 said and is now re-confirmed rather than revised.

### Evidence got overwritten, and the log noticed

An early version of the client named evidence files after the URL only, so a
later request to the same URL silently replaced an earlier body. The request log
kept claiming a SHA-256 for a file that no longer held those bytes, so 41 of 48
evidence files appeared to fail verification. Two things were wrong: the
storage could overwrite evidence, and the verifier was checking historical
entries against current files. Evidence is now content-addressed, and the
verifier only checks the current artefact per path, reporting the rest as
superseded rather than as corruption. Deletions are recorded as tombstones in
the log, because a delete that is not logged is indistinguishable from data
loss. Reporting 41 mismatches as if they were all corruption would have been
worse than the bug: it trains a reader to ignore the report.

**117 real requests** across 53 distinct URLs, against a 120 per-run cap that no
single run approached. The high total is re-fetching the same sitemaps while
parsers were corrected, not breadth of crawling. The log file holds many more
lines than that, because each `--offline` run appends one `replayed: true` record
per URL; an earlier entry here said "235 requests", which had counted those
replays as real traffic. The 53 distinct URLs figure was always correct.

**A false negative about Aldi, found by re-reading the archive.** Phase 3 reported
that Aldi Nord publishes no `basePrice` field, and Phase 1's records disagreed.
Phase 1 was right. `basePrice` is an array of objects nested inside
`currentPrice`, and the Phase 3 parser read `product['basePrice']` one level too
shallow, so it returned `None` and the report stated a field was absent while the
value sat in the same dict the parser had already read a shelf price from. Aldi
does publish per-unit prices: 11.32 EUR/kg on the 600 g chicken, 0.99 EUR/L on
the milk, 0.99 EUR/kg on the bananas. The parser is fixed, the raw HTML is
archived, and `verify_phase3.py` now re-derives the field from those bytes and
fails if the parser and the archive disagree. Recorded here because the failure
mode matters more than the bug: a parser that returns `None` for a field it
mis-reads is indistinguishable from a source that does not publish the field, and
that false negative had already removed unit-price comparison from the project's
capabilities.

### Where this leaves the project

**Not ready for a real-time multi-chain price comparison.** Live price coverage
is 1 of 6 chains, no retailer publishes a GTIN, and reuse permission is
unresolved for both responsive retailers.

Unblocked today, with no open legal question: store location, opening hours,
travel-time modelling, and total-cost arithmetic. That is also the defensible
differentiator, since the competitor research found existing basket optimisers
already treat the product as a basket and none of them model the trip.

Needs a person, not more requests: legal advice on Datenbankherstellerrecht and
UrhG, and a product decision about whether one live source plus crowdsourced
prices is enough to be worth building, or whether this needs a commercial data
partner.

### Things we did
- Replaced hand-copied numbers with evidence that a script can re-derive.
- Marked two earlier estimates as superseded instead of quietly fixing them.
- Reported a requested deliverable as unmet rather than padding the sample.
- Distinguished "no price published" from "price blocked", which are different
  problems with different fixes.
- Wrote down that the blocker is product identity, after two phases pointed at
  price availability.
