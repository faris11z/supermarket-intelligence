# Data Acquisition Spike - Raw Sample

Observed data from the supermarket data-acquisition spike (2026-09-30).

## Read this first

This directory contains **directly observed** fields only, captured with **67 HTTP
requests total** across six chains. Nothing here is synthetic, inferred-as-fact, or
hand-written. Where a value is absent, it is recorded as `null` with a `*_note`
explaining the absence, rather than being filled in.

## Contents

| File | What it is |
|---|---|
| `access_log.json` | Every request made, per-domain access verdict, and the specific constraints that were upheld |
| `aldi_nord_observed.json` | 5 Aldi Nord products extracted from server-rendered `__NEXT_DATA__` (2 original + 3 follow-up) |
| `lidl_observed.json` | 2 Lidl products extracted from JSON-LD `Product` schema |
| `store_locator_findings.json` | Store-locator + catalog follow-up: Lidl catalog composition, the Lidl grocery-price test, 10 Lidl Rostock stores with postcodes, and one Aldi Nord store page yielding lat/lng, postcode, opening hours and regional banner |
| `robots_snapshot/` | The `robots.txt` files actually retrieved, the Lidl sitemap index, plus the 403 error bodies for the blocked domains |

## How this data was obtained

* A single honest identifying User-Agent: `supermarket-intel-spike/0.1`.
* `curl` only. **No JavaScript was executed** and no headless browser was used.
* Product discovery used **only** the sitemaps that each site advertises in its own
  `robots.txt`. Onsite search endpoints that were `Disallow`ed were never called.
* **No** CAPTCHA solving, no user-agent spoofing, no proxy or IP rotation, no retry
  with altered request characteristics after a block, and no reverse-engineering of
  private APIs.
* When a domain returned 403, the spike **stopped for that domain and documented it.**

## Why full HTML pages were not archived

The retailer pages are copyrighted and, in Kaufland's case, the only response we could
obtain was a bot-verification page. Rather than store page HTML wholesale, this
directory stores a **curated extraction of the factual fields** we observed, plus
enough provenance (extraction path, source URL, HTTP status) that any finding can be
re-verified independently. The only raw artefacts retained are the `robots.txt` files,
which are published for exactly this purpose, and short 403 error bodies kept as
evidence that a block occurred.

## Known limitations of this sample

* **7 product pages total** (5 Aldi Nord, 2 Lidl). This is a feasibility probe, not a
  dataset. It cannot support any statistical claim about catalog size, price
  distribution or coverage.
* **Aldi Nord prices were captured for milk with a promotion valid 2026-10-01 to
  2026-10-03**, i.e. a future-dated promo relative to the collection time. Prices
  without a promotion were not sampled, so the ratio of promo vs. regular price is
  **Unknown**.
* **The Lidl records are wine and a cushion, not groceries.** See section 2 of
  `docs/research/supermarket-data-acquisition-spike.md`. They characterise the *page
  format* only and must not be read as grocery coverage.
* **Data licensing is unresolved and is the highest-priority open item.** Aldi Nord
  publishes no terms of use and no Impressum; the legal text is client-rendered and was not
  retrievable without executing JavaScript. Absence of a prohibition is not permission, and
  robots.txt is not a licence. These observations are cached here for research and
  prototyping only. See `licensing_review` in `access_log.json`.
* **No GTIN/EAN was observed on Aldi Nord pages.** Whether a barcode exists elsewhere
  in the site is **Unknown** - `/mds/` is robots-disallowed and was never requested.
* **The 5 Aldi Nord pages span 4 categories but 4 distinct optional-key schemas.**
  19 keys were present on every page; `brandName`, `promotionPrices`, `basePrice`,
  `legalInformation` and meta fields are optional and must be treated as nullable.
