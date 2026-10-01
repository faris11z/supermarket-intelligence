# Source suitability matrix

Phase 3, generated 2026-09-30. Every row was produced by a probe in
`research/`, and every "VERIFIED" cell corresponds to a request in
`data/research/request_log.jsonl` with a saved response body.

Reproduce: `python -m research.run_probe` then `python research/verify_phase3.py`.

## What the columns mean

- **Access** is a measured HTTP result, not a guess.
- **Prices** asks one question: can this source give a current price for a
  grocery product a user is actually shopping for?
- **GTIN** matters more than it looks. Without a barcode published by the
  retailer, matching "the same product" across chains is fuzzy name matching,
  which is exactly the kind of error a price comparison cannot afford.
- **Licence** is what the source's own terms say, not what we wish they said.
  "Unresolved" means nobody has established an answer, and it is not the same
  as "no".

## Retailer sources

| Source | Access | Current prices | GTIN | Store data | Licence | Verdict |
|---|---|---|---|---|---|---|
| Aldi Nord | 200 on permitted paths | **YES**, 4/4 parsed pages | **NO**, 0/4 | lat/lng + hours published | **UNRESOLVED** | **Only usable live price source** |
| Lidl | 200 on permitted paths | **NO**, 0/5, all `InStoreOnly` | **NO**, 0/5 | city pages give postcode-level lists | **UNRESOLVED**, terms found and read | Ruled out as a price source |
| Kaufland | Blocked in Phase 1/2 | not established | not established | not established | not established | Ruled out for now |
| Netto | No product catalogue | not established | not established | not established | not established | Ruled out for now |
| REWE | Blocked in Phase 1/2 | not established | not established | not established | not established | Ruled out for now |
| EDEKA | Blocked in Phase 1/2 | not established | not established | not established | not established | Ruled out for now |

**Live price coverage: 1 of 6 target chains.** That is the headline number, and
no amount of open-data substitution changes it.

## Open data sources

All six were actually requested. None of them is a live grocery price feed.

| Source | Access | Prices | Product identity | Store data | Licence | Verdict |
|---|---|---|---|---|---|---|
| Open Food Facts | PASS | none | **GTIN is the primary key** | none | ODbL 1.0, share-alike | Best matching backbone available |
| Open Prices | PASS, 318,982 observations | historical, crowdsourced | GTIN join key | partial, free-text | CC BY-SA 3.0 reported, not re-verified | Reference data only, not live |
| OpenStreetMap / Overpass | PASS but flaky (504s, timeouts) | none | none | shop nodes with address tags | ODbL 1.0 | Store fallback, snapshot only |
| plz_geocoord | PASS, 8,298 rows | none | none | postcode centroids only | **Apache-2.0 verified from primary source** | Usable fallback, 0.563 km error |
| Nominatim | PASS | none | none | address geocoding | ODbL 1.0 + usage policy | Not needed; 1 req/s limit |
| SMARD | PASS | electricity/gas only | none | none | **API spec verified open; data licence UNKNOWN** | **Wrong domain**, discard |

## Why the open sources cannot close the gap

Open Prices looks like the answer, and its licence is the most permissive of
anything we found. It fails for a coverage reason, not a legal one:

- 318,982 total observations, but only ~5.1% of German products appear in two or
  more chains, and only a few hundred products span enough chains to price a
  six-way basket.
- It is crowdsourced and historical. It cannot answer "what does this cost at the
  Aldi on my street right now".
- It is keyed by GTIN, and the retailers do not publish GTINs on permitted
  pages. So even a perfect Open Prices feed cannot be joined to a live Aldi
  scrape by anything better than a fuzzy name match.

That last point is the structural finding of this phase. **The missing GTIN, not
the missing price, is what blocks a cross-chain price comparison.** Aldi gives
prices without barcodes; Lidl gives barcodes without prices; Open Prices gives
barcodes with historical prices. No two of these join cleanly.

## Measured detail worth keeping

- Aldi exact store count: **2,236** in the advertised sitemap. The earlier
  estimate of 1,693 came from inferring a range from store IDs and was 543 low.
  It was never a measurement and is now superseded.
- Lidl advertised product catalog: **13,337** URLs, of which **5** are genuine
  food. The 48 candidates that survived automated filtering were each reviewed
  by hand: 24 alcohol, 12 plants and seedlings, 7 non-food gadgets, 5 food.
- Lidl's five food SKUs publish `InStoreOnly` and no price in JSON-LD. The only
  prices exist behind the store-selection path, which `robots.txt` disallows.
- `plz_geocoord` places postcode 18119 at 54.171828, 12.091058. The Aldi store
  on Lortzingstrasse 19a is at 54.16939, 12.083483. That is **0.563 km** of
  error, which is material when the product feature is travel cost.

## Recommendation

Stop looking for a public source of current grocery prices. The evidence says
there is not one, and the honest options are:

1. **Get legal advice first.** Reuse permission is unresolved for both Aldi and
   Lidl, and no amount of further technical probing will resolve it. This is a
   question about `Datenbankherstellerrecht` and `UrhG`, not about HTTP.
2. **Then choose a data strategy:** written permission, a commercial data
   partner, a commercial data broker, or a product that works with one live
   source plus crowdsourced prices.
3. **Build the part that is already unblocked.** Store location, opening hours,
   travel time and total-cost arithmetic are all solvable today and are the
   actual differentiator against generic basket-optimiser competitors.

A price comparison built on a single chain plus fuzzy matching would be worse
than no product: it would confidently quote a wrong number.
