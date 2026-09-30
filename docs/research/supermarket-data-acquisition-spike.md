# Supermarket Data Acquisition Spike

**Date:** 2026-09-30
**Scope:** Feasibility only. No production scraper was built.
**Total HTTP requests:** 42 across all six chains, including 5 product-detail pages.
**Raw sample:** [`data/raw/spike/`](../../data/raw/spike/)

## How to read this report

Every claim is tagged:

| Tag | Meaning |
|---|---|
| **[OBSERVED]** | Directly seen in a response body or status code. Reproducible. |
| **[INFERRED]** | A conclusion drawn from observed facts. Reasoning stated. |
| **[ASSUMPTION]** | Not verified. Flagged so it is not mistaken for evidence. |
| **[UNAVAILABLE]** | Could not be determined within this spike's constraints. |

No value in this report was invented to fill a gap. Where a field could not be
established, it says so.

---

# 1. Executive Summary

**Can we access useful product data?** Partially - and *not* for the chains that
matter most. **Four of six chains are inaccessible** to an ordinary client:
`aldi.de`, `edeka.de` and `netto-online.de` return HTTP 403 from an Akamai edge, and
`kaufland.de` returns a bot-verification interstitial ("Verifizierung erforderlich")
**[OBSERVED]**. `rewe.de` serves its `robots.txt` but answers every shop, product and
sitemap path with a 403 fallback page containing no product markup **[OBSERVED]**.
`netto.de` is fully crawlable but advertises **zero product pages** - its sitemap holds
560 URLs, all corporate and marketing pages **[OBSERVED]**.

**Can we access prices?** Yes, for exactly one chain in a useful form. **`Aldi Nord`
publishes a `robots.txt`-advertised catalog of 2,258 product URLs and serves complete
prices in plain server-rendered HTML** - no JavaScript, no login, no CAPTCHA **[OBSERVED]**.
The embedded payload includes current price, UVP reference price, **€/kg or €/L unit
price**, promotion label, and **promotion validity dates**. It also includes brand,
sales unit (e.g. `600-g-Packung`), category taxonomy, availability, deposit and
cold-chain flags, and quality seals. This is better structured data than anything in
the Phase 1 open datasets.

**Is price location-dependent?** For the one accessible chain, **no** **[OBSERVED]**.
Aldi Nord pages showed no postcode, store or market selector. By contrast Lidl's
JSON-LD declares `availability: "OnlineOnly"` **[OBSERVED]**. The genuinely
location-dependent question - "is it in stock at *my* branch, at *my* price" - was
**not testable**, because the chains that would answer it were all blocked.

**Which chains are technically feasible?**

| Chain | Verdict |
|---|---|
| **Aldi Nord** | **Feasible** - rich structured data, robots-sanctioned, no protection |
| Lidl | Feasible **mechanism, wrong catalog** - see below |
| Netto | Not feasible - no product catalog exists on the accessible domain |
| REWE | Not feasible - edge-blocked on all content paths |
| Aldi (aldi.de / Aldi Süd) | Not feasible - edge-blocked |
| Kaufland | Not feasible - active bot verification |
| EDEKA | Not feasible - edge-blocked; candidate shop domains do not resolve |

**The single most important finding is a trap, not a win.** Lidl looks like the best
technical result: server-rendered, clean JSON-LD, **GTIN-13 barcodes present**, and
even per-product `aggregateRating` (54 reviews, 4.5 stars on the wine we sampled)
**[OBSERVED]**. But `lidl.de` is **not a general grocery shop**. Its advertised catalog
of 13,337 product URLs contains **no milk, no eggs, no butter, no pasta, no flour, no
bananas, no chicken** - substring searching for our whole test basket returned only
false positives such as *Butterbirne* (a pear cultivar), *Eierlikör* (egg liqueur),
*Reißverschluss* (zipper) and *Speierling* (fir tree) **[OBSERVED]**. The catalog is
dominated by wine (~962 URLs), non-food goods (~916) and coffee equipment (~289)
**[INFERRED from slug analysis]**. Choosing Lidl because its JSON-LD is the prettiest
would have wasted the entire project.

**Major blockers:** (1) EDEKA, Aldi Süd, REWE and Kaufland are behind bot protection we
will not circumvent; (2) the two hardest chains to match are precisely the two we can
see least of; (3) **no GTIN on Aldi Nord**, so product matching must be name-based and
is therefore the component most likely to need ML; (4) 2,258 Aldi Nord products is a
*sortiment overview*, not a full live price list.

**Bottom line:** This moves the project from *"no usable data exists"* to *"one chain
has excellent, legally clean, machine-readable prices"*. That is a real gain, and it is
not enough for a six-chain comparison.

---

# 2. Supermarket-by-Supermarket Findings

| Supermarket | Product data | Price | Product ID | GTIN | Unit price | Location dependency | Access difficulty | Notes |
|---|---|---|---|---|---|---|---|---|
| **Aldi Nord** | **Yes** - 2,258 URLs | **Yes** | **Yes** (`9545`) | **No** | **Yes** (€/kg, €/L) | **No** (none observed) | **Low** | Best result. Robots-advertised catalog; server-rendered; promo + UVP + validity dates |
| **Lidl** | **Partial** - 13,337 URLs, but **no fresh groceries** | **Yes** (JSON-LD) | **Yes** (`p100181707`) | **Yes** (gtin13) | **No** | **No** (`OnlineOnly`) | **Low** | Wrong catalog: wine/non-food/plants, not groceries |
| **Netto** | **No** - 560 URLs, 0 products | No | No | No | No | Unknown | **Low** (open) but pointless | `netto.de` is a corporate site; real shop `netto-online.de` is 403 |
| **REWE** | **No** | No | No | No | No | Unknown | **High** | `robots.txt` served; all content paths 403 |
| **Aldi** (`aldi.de`, Aldi Süd) | **No** | No | No | No | No | Unknown | **High** | Akamai 403 on `robots.txt` itself |
| **Kaufland** | **No** | No | No | No | No | Unknown | **High** | Explicit bot-verification challenge; not bypassed |
| **EDEKA** | **No** | No | No | No | No | Unknown | **High** | Akamai 403; `edeka-online.de` / `shops.edeka.de` do not resolve |

Legend: **Yes** = observed working · **Partial** = works but with a limiting gap ·
**No** = observed not to be available · *Unknown* = could not be determined within
this spike's constraints.

**On Aldi Nord's "No" for GTIN:** the product pages carried no barcode field
**[OBSERVED]**. Whether a GTIN exists elsewhere on the site is **Unknown** - this spike
did not probe beyond the product page. This matters a great deal and is carried into
section 8.

---

# 3. Sample Data

Only genuinely observed fields. Sourced from
[`data/raw/spike/`](../../data/raw/spike/).

| supermarket | product | quantity | price | product_id | url |
|---|---|---|---|---|---|
| Aldi Nord | Frische Milch (BÄRENMARKE) | 1 L | €0.99 (UVP €1.59, −37%, promo 01-03 Oct 2026) | 9545 | `aldi-nord.de/produkt/frische-milch-9545.html` |
| Aldi Nord | Hähnchenbrustfilet-Teilstücke (MEINE METZGEREI) | 600 g | €6.79 (no promo) | 8998 | `aldi-nord.de/produkt/haehnchenbrustfilet-teilstuecke-8998.html` |
| Aldi Nord | Weizenmehl (BÄRENMARKE) | 1 kg | €0.59 (no promo) | 510 | `aldi-nord.de/produkt/weizenmehl-510.html` |
| Aldi Nord | Bananen | by weight | €0.99/kg (UVP €1.29, promo) | 6151 | `aldi-nord.de/produkt/bananen-6151.html` |
| Aldi Nord | Langkorn Reis (BÄRENMARKE) | 750 g | €2.49 (UVP €3.79, promo) | 5474 | `aldi-nord.de/produkt/langkorn-reis-5474.html` |
| Lidl | Breisacher Vulkanfelsen Spätburgunder, Rotwein | 1 l *(inferred from name)* | €5.49 | p100181707 | `lidl.de/p/.../p100181707` |
| Lidl | f.a.n. Kissen (non-food) | not exposed | €32.99 | p100198362 | `lidl.de/p/.../p100198362` |

**Unit-price arithmetic verified on 4 of 5 Aldi Nord records** **[OBSERVED]**:
chicken €6.79 ÷ 0.600 kg = €11.32/kg ✓; rice €2.49 ÷ 0.750 kg = €3.32/kg ✓; milk
€0.99 ÷ 1 L = €0.99/L ✓; bananas are sold by weight (`kg-Preis`), so the displayed €0.99
*is* the €/kg ✓. Only **Weizenmehl had no `basePrice` key at all** - for a 1 kg pack it
must be computed (€0.59/kg). A missing `basePrice` must therefore **not** be treated as
a missing unit price.

**Sampling bias:** 3 of the 5 Aldi Nord products are on promotion, so this sample
over-represents promotional pricing. The true promo rate across the catalog is
**Unknown**.

**6 of the 8 requested test products were retrieved**, all from Aldi Nord - the other
two (pasta, and eggs as a distinct staple) were simply not sampled. Aldi Nord's
sitemap does contain matching candidates (e.g. `weizenmehl`, `eierspaetzle`); we capped
the sample at 5 pages for this chain.

---

# 4. Technical Architecture Observations

### Aldi Nord - server-rendered Next.js with a stringified JSON payload

**Mechanism** **[OBSERVED]**: a plain `GET` returns ~76 KB of HTML. The product data
sits in `<script id="__NEXT_DATA__">`, under
`props.pageProps.apiData` - but `apiData` is a **stringified JSON blob**, not a live
object, so naive `json.loads` + key traversal finds nothing. Inside it is a two-entry
list, `[PAGE_MGNL_GET, PRODUCT_DETAIL_GET]`, and the product sits at
`PRODUCT_DETAIL_GET.res.products[0]`.

This matters for any future pipeline: the obvious extraction path silently returns zero
results. The correct path requires a second `json.loads` on a nested string.

Fields observed per product **[OBSERVED]**:

```
objectID, name, productSlug, brandName, shortDescription, salesUnit,
isAvailable, isComingSoon, isRecall, isDepositProduct, depositValue,
isCooling, isFreezing, categoryIDs[], mainCategoryID,
currentPrice { priceValue, strikePrice{ strikePriceValue, strikePriceLabel },
               basePrice[{ basePriceValue, basePriceScale }], priceTagLabels,
               validFrom, validUntil },
promotionPrices[{ ..., validFromLocalDate, validUntilLocalDate }],
assets[{ type, url }]  // primary image + attribute seals
```

Three points of genuine quality **[OBSERVED]**:

1. **German unit price is present and structured** (`basePriceScale` = `kg` / `Liter`).
   This is the legally mandated Preisangabenverordnung base price, and receiving it
   machine-readable removes the single largest source of product-matching error. It is
   *sometimes* omitted, however - the 1 kg Weizenmehl had no `basePrice` - so unit price
   must be computed when absent rather than treated as missing.
2. **Reference price is labelled `UVP`** (unverbindliche Preisempfehlung). Promotional
   vs. regular price is therefore recoverable, which the open datasets do not support.
   Observed rule: `strikePrice` was present on all 3 promoted products and absent on both
   unpromoted ones, so its presence is a reliable promotion flag.
3. **`validFromLocalDate` / `validUntilLocalDate`** give an explicit promo window. The
   chicken record's validity window spans ~14 months **[INFERRED]**, consistent with a
   standing shelf price rather than a promotion - so an unpromoted product can be
   distinguished from a temporarily discounted one.

**Extraction stability was tested deliberately** **[OBSERVED]**: 5 pages spanning 4
categories (chilled dairy, fresh meat, dry staples, fresh produce) parsed **5 of 5**
successfully, using the same code path. 19 core keys were present on all 5. However,
**4 distinct optional-key schemas** were observed, which a production parser must
survive:

| Key | Absent on | Consequence |
|---|---|---|
| `brandName` | Bananen | own-brand produce may have no brand → matching must tolerate a null brand |
| `promotionPrices` | 2 unpromoted products | key presence is the promotion flag; absence is normal, not an error |
| `basePrice` | Weizenmehl | unit price must be computed |
| `legalInformation` | Weizenmehl | footnote handling must be optional |
| `metaTitle` / `metaDescription` | 4 of 5 | SEO fields are the exception, not the rule |

**Quantity normalisation has a real edge case** **[OBSERVED]**: Bananen is sold
`kg-Preis` - by weight, with no fixed pack. A shopping-list line "1 kg bananas" maps
directly to the €/kg figure, but any logic that assumes every product has a
`NNN-g-Packung` will break on fresh produce.

### Lidl - server-rendered HTML with JSON-LD

**Mechanism** **[OBSERVED]**: a plain `GET` returns ~415-438 KB of complete HTML
containing 3 `application/ld+json` blocks, including `@type: "Product"`. Fields:
`sku`, `gtin13[]`, `name`, `description`, `image[]`, `url`, `brand`, `offers[]` (with
`price`, `priceCurrency`, `availability`), and `aggregateRating`. Also `Organization`
blocks.

Technically the cleanest integration in the whole spike - standard schema.org,
discoverable via the advertised sitemap, no protection. **But the catalog is the wrong
one for this project** (section 1). A note for the sentiment phase: `aggregateRating`
with `ratingCount` and `reviewCount` exists, so *per-product ratings* are available on
Lidl. No review **text** was retrieved, so this is not yet a sentiment dataset.

### Netto - crawlable, but no catalog

**Mechanism** **[OBSERVED]**: `robots.txt` is `Allow: /` - completely permissive - and
`sitemap.xml` is served. But all 560 URLs are corporate or marketing paths
(`angebote`, `prospekte`, `marktsuche`, `netto-eigenmarken`, `karriere`, `presse`,
`impressum`, `rezepte`, `nachhaltigkeit`). Zero product URLs. This is a low crawl
barrier with no catalog behind it; the actual grocery shop lives on
`netto-online.de`, which is 403.

### REWE - `robots.txt` readable, content edge-blocked

**Mechanism** **[OBSERVED]**: `robots.txt` is served in full and is unusually detailed -
it `Disallow`s `/restservices/`, `/*?searchString=`, `/shop/mc/`, `/shop/checkout/` and
pagination params, while explicitly `Allow`ing ~20 `/angebote/...` category paths. We
requested one of those explicitly allowed paths. It returned **403 with a 251 KB HTML
body whose `<title>` is "REWE Onlineshop"** - a generic fallback, containing no
JSON-LD, no GTIN and no prices. The same 403 was returned for the sitemap. So the
`robots.txt` is a red herring: being readable does not imply content is reachable.

### Aldi (aldi.de, Aldi Süd), EDEKA, Kaufland - blocked, not worked around

**[OBSERVED]** `aldi.de` and `edeka.de` return 403 on `robots.txt` itself, with Akamai
reference links (`errors.edgesuite.net`). `kaufland.de` returns 403 with the title
"Verifizierung erforderlich" - an active verification challenge. `netto-online.de`
returns 403 on `robots.txt`. Candidate EDEKA shop domains (`edeka-online.de`,
`shops.edeka.de`) do not resolve at all (curl exit 000).

In each case the spike **stopped and recorded the block**. No challenge was solved, no
browser fingerprint was spoofed, no proxy was used, and no retry was made with altered
request characteristics.

**Net note:** `Aldi Nord` and `Aldi Süd` are separate legal operators with separate
sites. The accessible catalog is therefore **Aldi Nord's only** - it says nothing about
Aldi Süd, and Aldi Nord covers only part of Germany **[INFERRED]**.

---

# 5. Legal / Access Considerations

**This section records publicly visible facts. It is not legal advice.**

### Facts observed

* All four accessible/blocked boundaries above are **technical**, not contractual, and
  were reached without bypassing anything.
* `lidl.de` explicitly disallows onsite search (`Disallow: *search?q=*`) plus
  `/user-api/*`, `/cqe/*`, `*idsOnly=*`, `*productsOnly=*`, `*sort=*` **[OBSERVED]**.
  We did not request those; we used the advertised sitemap instead.
* `rewe.de` disallows search and internal endpoints, and allows named `/angebote/`
  paths **[OBSERVED]**.
* `aldi-nord.de` disallows `/bal/`, `/can/`, `/mds/` and some form paths, and
  advertises sitemaps including a dedicated products sitemap **[OBSERVED]**. We
  requested only `/produkt/` and the advertised sitemaps.
* Aldi Nord serves a **product-rating** and **review-related** signal; we retrieved
  structured pricing only, no customer text.
* Aldi Nord's product page includes a `legalInformation` block with footnotes
  (`footnote1`, `footnote2`) **[OBSERVED]**. Whether any of these impose redistribution
  restrictions is **[UNAVAILABLE]** - we did not enumerate them.

### Interpretation (clearly separated)

* Publishing a `robots.txt` and a `sitemap.xml` that includes a product sitemap is a
  strong signal that automated product discovery is *expected*. It is **not** a licence
  grant. The applicable terms of use and any commercial-use conditions are
  **[UNAVAILABLE]** - we did not retrieve or analyse them, and that should happen
  before any production ingestion.
* The most legally valuable discovery in this spike is not Lidl's JSON-LD but
  **Aldi Nord's sitemap-published product catalog**: it is a deliberate, machine-readable
  publication channel, which is a far better footing than scraping a search interface.
* The four blocked chains are signalling that automated access is unwanted. Given the
  project explicitly asks us to respect access restrictions, the correct engineering
  consequence is to **exclude them from direct ingestion**, not to find a workaround.

---

# 6. Data Quality

* **Missing fields - the big one is GTIN.** Aldi Nord exposed **no barcode** on any of
  the 5 sampled products **[OBSERVED]**. This was established exhaustively rather than
  assumed: every 8-14 digit numeric token on all 5 pages was scanned (none found), the
  keywords `gtin`/`ean`/`barcode`/`gtin13`/`articleNumber`/`artikelnummer`/`vendorCode`
  were searched (only 3 `'ean'` substring hits per page, which are false positives inside
  words like *Clean*, *Cream* and *Mean*, not a field), and all 24 product-object keys
  were enumerated (no barcode key). Lidl *did* expose `gtin13` **[OBSERVED]**. This
  asymmetry is decisive: GTIN is the only *exact* join key between chains. Without it,
  matching "Frische Milch" to a REWE or Kaufland equivalent is **inference, not lookup**
  - which is exactly where the ML matching component earns its place.
* **A GTIN may exist behind a robots-disallowed path.** `/mds/` is disallowed in Aldi
  Nord's `robots.txt` and is plausibly a master-data service - the most likely home of a
  barcode. It was **not** probed **[OBSERVED]**. So the precise claim is *"no GTIN on
  permitted pages"*, not *"no GTIN on the site"*. Worth noting that `/ua-bot.html` is
  also disallowed despite its name.
* **Promotional vs. regular price is separable on Aldi Nord** (UVP strike price +
  `promoText1` + validity window) **[OBSERVED]**. This is a genuine advantage: a basket
  computed from promo prices is not comparable to one computed from everyday prices, so
  a naive "cheapest basket" would be measuring promotion calendars, not value.
* **Regional prices: Unknown.** Aldi Nord showed no location selector, so prices appear
  national **[OBSERVED]**. But Aldi Nord is a *regional operator* (northern Germany), so
  this may reflect chain scope rather than genuinely uniform national pricing
  **[INFERRED, unverified]**.
* **Availability is a single boolean** (`isAvailable`) **[OBSERVED]** - not per-branch
  stock. So "in stock at my store" remains **unanswerable** from this source. This is
  the largest functional gap versus the "where should I shop **today**" question.
* **Catalog scope: 2,258 URLs is a sortiment overview, not a live price list.** The
  sampled pages were partly promotional, and Aldi rotates offers weekly. Treat 2,258 as
  an upper bound on a single snapshot, not a daily full catalog.
* **Own-brand is the matching obstacle.** Sampled brands were `BÄRENMARKE` and
  `MEINE METZGEREI` **[OBSERVED]** - private labels that exist in no other chain. So a
  meaningful share of Aldi Nord's catalog is *permanently* unmatched to competitors, and
  cross-chain coverage will be structurally lower than the raw catalog size suggests.
* **Pack-size normalisation is essential.** `600-g-Packung` vs. `1-L-Packung` vs. 1 kg
  require unit conversion before any comparison **[OBSERVED]**. Aldi Nord pre-supplies
  €/kg, which mitigates this; a future source without base price would not.
* **Freshness: partially good.** Promo validity windows are explicit and in local dates
  **[OBSERVED]**, so staleness is detectable per record rather than assumed.
* **Duplicate risk: Unknown.** No attempt was made to detect duplicates, since that
  requires more than 2 records.
* **One methodological caveat, stated plainly:** the Aldi Nord milk price was captured
  with a promotion dated **2026-10-01 to 2026-10-03**, i.e. starting *after* collection.
  The promo/regular price ratio across the catalog is therefore **Unknown** - we must not
  extrapolate €0.99 milk prices as typical.

---

# 7. Recommendation

## **Option B - Direct supermarket data is feasible for some chains but not others.**

Specifically: **feasible for exactly one chain (Aldi Nord)**, technically feasible but
catalog-mismatched for a second (Lidl), and **not feasible for four** (Netto, REWE,
Aldi Süd, Kaufland, EDEKA) within the constraint of not circumventing protections.

**Why not A (all feasible):** four chains are behind bot protection we have committed
not to bypass, and one has no product catalog on its accessible domain.

**Why not C (insufficient, go fully licensed/open):** that would discard a real
asset. Aldi Nord gives us something the open datasets cannot: unit prices, UVP reference
prices, and promotion validity windows, from a sitemap-published, unprotection-free
source. Abandoning it entirely is premature.

**Why not D (more investigation required):** investigation is required - but *not*
before acting. The decisive unknowns are already specific and answerable cheaply, and
blocking on them would stall the project. Concretely, the four things worth checking
next, in order of value:

1. **Is a GTIN obtainable for Aldi Nord anywhere** (page metadata, sitemap, or another
   permitted endpoint)? This is the single highest-value unknown, because it decides
   whether cross-chain matching is lookup or inference.
2. **Aldi Süd coverage** - the other half of the Aldi footprint is a separate operator
   and is currently 403.
3. **Whether REWE's 403 is consistent** across sessions and paths, or intermittent. One
   sample of one allowed path cannot distinguish a hard block from a soft one.
4. **Aldi Nord terms of use**, and what the `legalInformation` footnotes restrict.

The honest framing of our current position: we have moved from *"no usable data"* to
*"one excellent chain"*. That is progress, and it is not a six-chain comparison.

---

# 8. Impact on Project Architecture

Deliberately scoped to implications only - no redesign.

**Ingestion.** The Phase 1 assumption of uniform retailer feeds is dead. Chains differ
in *kind*, not just degree: one exposes a sitemap-published catalog with embedded JSON,
one exposes JSON-LD with a wrong catalog, one exposes nothing. Ingestion must therefore
be **one adapter per source, with per-source capability flags** (exposes GTIN? exposes
unit price? exposes promo window?), and a chain registry recording `accessible` /
`blocked` / `no_catalog` with the evidence. Never model "supermarket" as a uniform
entity.

**Product matching.** This is the component the spike reprioritised most sharply. The
data gives us brand, name, sales unit and unit price, but the join key is missing on
our one good source. Matching must therefore run **deterministic-first** (exact name +
brand + normalised unit, then €/kg bucketing to align pack sizes) and escalate to
**fuzzy/embedding matching** only for the residual. This is the clearest justification
for ML in the project so far - and it comes from a *data* finding, not a modelling
preference. Treat match confidence as a first-class output; a basket total built on
uncertain matches is not a price claim.

**Price engine.** The distinction between promotional and regular price becomes
first-class. Because Aldi Nord exposes both, the engine should compute **two basket
totals** - "today's advertised price" and "everyday price (UVP)" - and label which one
it is showing. Reporting a promo-inflated "cheapest basket" as the answer would be
misleading. Unit price also enables per-kg/l comparison, which is the only way to
compare a 600 g pack against a 1 kg pack fairly.

**Database.** Needs columns we had not planned: `unit_price` + `unit_price_scale`,
`reference_price` + `reference_price_label`, `promo_valid_from` / `promo_valid_until`,
`is_available`, `is_recall`, `deposit_value`, and a `source_chain` + `source_url` +
`retrieved_at` provenance triple. `is_recall` and `deposit_value` matter commercially -
a recalled or deposit-bearing product must be excluded from a recommendation. Add a
**coverage/completeness** table so a chain can be marked `blocked` rather than silently
contributing zero prices, which would otherwise look identical to "chain is expensive".

**Historical price storage.** Now genuinely feasible, and better than Phase 1 assumed,
because records carry explicit validity windows. Price history can be reconstructed
from `validFrom`/`validUntil` rather than inferred from successive scrapes - meaning we
need only capture each *state change*, not poll continuously.

**MLOps.** The real change is in what gets versioned. DVC/MLflow tracking should key on
the **source snapshot** (sitemap URL + retrieval timestamp + content hash), because
retailer pages are mutable and unpinned; a model evaluated against yesterday's page is
not evaluated against today's. Add a **schema-drift check** on the embedded JSON
structure - this spike already showed how brittle that is, since the price payload is a
*stringified* blob inside `__NEXT_DATA__` that a naive parser silently misses. A silent
zero-row extraction is the failure mode to guard against.

**API.** The response must expose match confidence and data completeness, not just a
basket number. A user asking "where should I shop?" deserves to know that only one of
six chains was actually observed, and that several basket lines rest on inferred
product matches. Returning a single confident "buy at Aldi, €X" would misrepresent the
evidence. An honest API returns a ranked comparison plus explicit `chains_unavailable`
and per-line match confidence.

**Sentiment.** Lidl's `aggregateRating` is a genuine, unexploited lead for per-product
ratings **[OBSERVED]** - but ratings are not sentiment, and no review text was
retrieved. This does not change the Phase 1 conclusion that review data remains the
weakest link. It does suggest a cheap, honest fallback: per-product star ratings, clearly
labelled as ratings rather than sentiment, if aspect-based sentiment proves
unobtainable.

---

# 9. Decision Gate

> **Note:** question 3 of the original brief was truncated mid-sentence
> ("Can we …"). It is **not** answered here, because guessing the intended question
> would risk answering a different one. Please supply the full text of Q3.

**1. Can we obtain current prices from at least 3 supermarkets?**
**No.** We obtained *usable* current prices from **one** supermarket (Aldi Nord). Lidl
exposes prices for wine and non-food, not groceries, so it does not count toward the
grocery basket. Netto, REWE, Aldi Süd, Kaufland and EDEKA served no product data at
all. The threshold of 3 is **not met**.

**2. Can we obtain enough product metadata to perform product matching?**
**Yes for one chain, with a measured caveat about the other five.**

*Our accessible chain (Aldi Nord):* name, brand (nullable), sales unit, category
taxonomy, unit price, promo state and attribute flags for 2,258 products **[OBSERVED]**.
**But no GTIN** on any of 5 sampled pages **[OBSERVED]**. So Aldi Nord alone gives us
metadata rich enough to *attempt* matching but not an exact join key.

*The other five chains, via Open Prices:* here an earlier working assumption had to be
**retracted**. A first pass suggested ~78% of cross-chain products had no name, which
turned out to be an artifact of the Open Prices price export not carrying product names
(product names live in a separate products table). Re-measured against the products
table on a random sample of **30 of the 388 cross-chain GTINs** **[OBSERVED]**:

| Field available | Rate |
|---|---|
| product name | 30/30 (100%) |
| brand | 30/30 (100%) |
| name + brand together | 30/30 (100%) |
| quantity | 30/30 (100%) |
| category | 29/30 (97%) |

So **name-based matching is viable on Open Prices** - but the qualifying number is not
388 of 7,559, it is **388 of 7,559 = 5.1% of all DE products**. Two real limits remain:
the cross-chain set is small, and the sampled names are messy and off-domain (Listerine
mouthwash, instant noodles, partial names like "Vegetable Flavour"). A name-based
matcher would work, on ~5% of products, and would need category filtering to avoid
nonsense matches.

**Net answer:** enough metadata exists to build and *evaluate* a deterministic matcher
against ground-truth GTIN joins, and enough to justify a learned matcher for the
residual. What we do **not** have is a GTIN on our own best source, so live cross-chain
matching is inference-based there.

**3. _Truncated in the brief - not answered. Please provide the full question._**

---

## Appendix - Evidence and compliance

* **Requests:** 42 total, 5 product-detail pages, no headless browser, no JS execution.
* **Discovery:** exclusively via `robots.txt`-advertised sitemaps.
* **Not done:** no CAPTCHA solving, no UA spoofing, no proxy/IP rotation, no retry after
  a block, no private-API reverse engineering, no disallowed-path requests, no
  large-scale crawling. Aldi Nord's disallowed `/mds/` and `/ua-bot.html` were identified
  and deliberately left alone.
* **Separately:** 30 read-only queries against the Open Prices *research* API
  (`prices.openfoodfacts.org`) to correct a matching measurement, plus the Phase 1 bulk
  dataset downloads. These are open-data research queries, not retailer crawling.
* **Artifacts:** `access_log.json` (per-domain verdicts and the blocked 403 bodies),
  `aldi_nord_observed.json`, `lidl_observed.json`, `robots_snapshot/`, `README.md`
  (provenance and limitations).
* **Reproduce:** every claimed value in section 3 traces to a stored record with its
  source URL, extraction path and HTTP status.
