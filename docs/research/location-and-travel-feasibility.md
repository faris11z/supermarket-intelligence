# Location and Travel Feasibility

**Phase 2 research - date: 2026-09-30**
**Status: research only. No production code, no optimizer, no ingestion pipeline was built.**

---

## 0. Scope and what changed about the project

Phase 1 concluded that a six-chain, price-only basket comparison is not buildable from
open data: Open Prices covers the six chains with only ~5.1% cross-chain product
overlap, and direct scraping is realistically available for Aldi Nord only.

This phase asks a different question:

> Given a **postcode**, a **shopping list with quantities**, and a **transport mode**,
> what is the cheapest way to buy everything - and does travelling to a second store
> pay for itself?

That reframes the project from *price comparison* to **total shopping cost**, where the
basket subtotal is only one term. It also turns out to change the data problem, because
price data alone cannot answer the question.

### Evidence grading used throughout

| Tag | Meaning |
|---|---|
| **VERIFIED** | Directly observed in this research session, with the request recorded in Appendix A. |
| **PUBLISHED** | Stated by the source owner in its own documentation or publications, not independently re-measured here. |
| **INFERRED** | A conclusion drawn from verified observations. Reasonable, but not itself observed. |
| **ASSUMPTION** | A modelling choice. Must be made configurable, and must be visible in output. |
| **UNKNOWN** | Could not be established within this research. Explicitly open. |

No figure in this document is filled in from memory. Where a number is not available it
says **UNKNOWN**.

### Method and boundaries

* A single honest identifying User-Agent (`supermarket-intel-research/0.1`) was used for
  every request in this phase.
* Only small, bounded queries: single geocoding lookups, small bounding boxes, one-week
  price windows. **No bulk downloads, no full-catalog crawls, no spidering.**
* No CAPTCHA solving, no user-agent spoofing, no proxy rotation, no retry-after-block
  with altered request characteristics.
* Public demo routing services were used for *capability probing only*, not as a data
  source, and their limits are documented as real constraints in section 3.
* Per-request logging was not instrumented for this phase; endpoints and the purpose of
  each are listed in Appendix A rather than a fabricated total.

---

## 1. Postcode → coordinates

**Question: can a 5-digit German postcode be resolved to a usable coordinate offline or
via a free API?**

### Finding: yes, and a static file is the better option.

**VERIFIED.** `WZBSocialScienceCenter/plz_geocoord` provides a single flat CSV
(`plz_geocoord.csv`, header `,lat,lng`) with **8,298 postcode rows** and a geographic
centroid per postcode. The repository ships an **Apache License 2.0** `LICENSE` file.
Size 245,585 bytes. All five test postcodes used in this research were present:
`18055`, `20095`, `10115`, `80331`, `50667`.

**PUBLISHED.** The PLZ values are derived from the *Gemeindeverzeichnis* of the
Statistisches Bundesamt (Federal Statistical Office), and the coordinates are
geographic centroids of the postcode area.

**VERIFIED.** The OpenPLZ API resolves localities and administrative hierarchy without
coordinates:
`GET https://openplzapi.org/de/Localities?postalCode=18055` returned HTTP 200 with
`postalCode`, `name` (`Rostock`), `municipality` (key `13003000`, type
`Kreisfreie Stadt`), `district` (key `13003`) and `federalState` (key `13`,
`Mecklenburg-Vorpommern`).

**VERIFIED.** Nominatim resolved all five test postcodes to coordinates. The
`state`/`state_code` fields were **omitted** for the city-state postcodes (`10115`
Berlin, `20095` Hamburg).

### Assessment

| Source | Latency | Cost | Licence | Verdict |
|---|---|---|---|---|
| `plz_geocoord` CSV | None (local) | None | Apache-2.0 | **Recommended** - pin a version, no runtime dependency |
| OpenPLZ API | Network | Free, rate-limited | ODbL-1.0 (data repo) | Good for admin hierarchy + validation, **no coordinates** |
| Nominatim | Network | Free, strict UA policy | ODbL | Fallback only; do not call per request |

**INFERRED.** A postcode *centroid* is a poor proxy for a user's actual position. German
postcode areas can span several kilometres, and in dense cities one postcode can cover
both a suburban edge and a city centre. Any distance-based recommendation is therefore
noisy at the sub-kilometre scale.

**Recommendation.** Resolve the postcode to a centroid for *candidate generation*, but
let the user set an exact start point (map pin, or device geolocation) before the
recommendation is finalised. Treat centroid-derived distance as an estimate and label it
as such in the output.

**UNKNOWN.** Street-level address geocoding, and the licensing/commercial terms of the
OpenPLZ API service itself (as opposed to its ODbL data repository).

---

## 2. Branch (store) data

**Question: can we locate the stores of the six target chains near a postcode, with
enough completeness to plan a trip?**

### 2.1 OpenStreetMap / Overpass is the only viable open source

**VERIFIED.** An Overpass query over a Rostock bounding box
(`54.05,12.05,54.20,12.25`) returned **123 grocery features** and included all six
target chains by name. Observed tag completeness across those 123 features:

| Tag | Present |
|---|---|
| name, coordinates | 100% |
| `opening_hours` | 97% |
| `brand` | 72% |
| `addr:street` / `addr:housenumber` | 76% |
| `addr:postcode` | 75% |
| `addr:city` | 73% |
| `website` | 29% |
| phone | 13% |

**VERIFIED.** A second query over a Berlin bounding box returned **110** grocery
features, again including all six chains: EDEKA 22, REWE 15, Netto 10, Lidl 7, Aldi 7,
Kaufland 1, other/unnamed 48.

**VERIFIED.** A nationwide count query on a different Overpass instance returned
**21,523** matching features (8,857 nodes, 12,632 ways, 34 relations).

**UNKNOWN - and important.** 21,523 is **not** a store count. It is a count of OSM
features matching a name filter. It will contain duplicates, closed stores, and chains
outside the six targets. The per-chain national breakdown was **not** obtained, because
the main Overpass endpoint returned `504 Gateway Timeout` on the national query and a
mirror instance returned empty results for German coordinates. This number must not be
quoted as "German stores" anywhere.

**INFERRED.** The Rostock/Berlin samples show that OSM has enough coverage to be useful
in cities, and that `addr:postcode` at 75% completeness is sufficient for a
"stores near this postcode" filter. The 29% `website` rate is a problem for anything
that wants to link out to a chain's own store page.

**INFERRED.** The 48-of-110 "other" features in Berlin are largely independents
(whole-food shops, organic bakeries, late-night shops). The project will need a
retailer-identity resolution step to map an OSM feature to a chain, and to decide what to
do with independents. This is the same class of problem as product matching, one level up.

### 2.2 Per-chain branch data from the retailers themselves

Phase 1 (`docs/research/supermarket-data-acquisition-spike.md`) established that only
Aldi Nord is reliably reachable. That finding holds for branch data:

* `netto.de` advertises a `marktsuche` (store search) section and is fully crawlable
  (`User-Agent: *` / `Allow: /`), but it is a **corporate** site with no product catalog.
  It is the most promising per-chain branch source of the six.
* Aldi/EDEKA/Kaufland/REWE/`netto-online.de` remain 403 or challenge-gated.

**UNKNOWN.** Whether Aldi Nord, Lidl, REWE, EDEKA, Kaufland and Netto each publish
machine-readable branch locators (JSON endpoints, sitemaps of store pages, or
schema.org markup) on their store-finder paths. Phase 1 did not test store-finder paths,
only product paths. This is the single highest-value untested source.

#### Update 2026-09-30 (later in the same day) - Lidl is solved, and it changes the answer

The untested source was tested. **VERIFIED.** Lidl publishes both a product sitemap and
a **store sitemap**, both advertised in its own `robots.txt`:

| Lidl artefact | Result |
|---|---|
| `https://www.lidl.de/static/sitemap.xml` (index) | 200 - declares product, pages, **stores**, brands, nqps sitemaps |
| `https://www.lidl.de/p/export/DE/de/product_sitemap.xml.gz` | 200 - **13,337** product URLs |
| `https://www.lidl.de/s/de-DE/filialen/sitemap.xml` | 200 - **3,669** store URLs (3,665 store-detail + 395 city index pages) |

**VERIFIED - the store→postcode problem is solved for Lidl, in server-rendered HTML.**
Store URLs are `/s/de-DE/filialen/{city-slug}/{street-slug}/`, but the city index page
carries the mapping explicitly. Each store is one anchor whose `aria-label` is
`Lidl Filiale {street}, {PLZ} {city}`:

```
/s/de-DE/filialen/rostock/  ->  10 stores extracted, each with a valid 5-digit postcode
   Schiffbauerring 1, 18109 Rostock        Maxim-Gorki-Str. 66/67, 18106 Rostock
   Warnowallee 20 a, 18107 Rostock         Neubrandenburger Str. 10-11, 18055 Rostock
   ... (10 total)
```

No JavaScript execution is required. The page has **no** latitude, longitude,
`openingHours` or schema.org markup, but the postcode is enough to join the
`plz_geocoord` centroid file from §1, so this is a complete store-locator source.

**VERIFIED - but Lidl is simultaneously ruled out as a price source.** The 13,337-product
catalog is overwhelmingly general merchandise and alcohol. The largest own-brand families
are `esmara` (clothing, 1,746), `livarno` (furniture, 1,138), `parkside` (tools, 1,117),
`crivit` (sportswear, 794), `lupilu` (baby, 657) and `silvercrest` (kitchenware, 531) -
roughly 55% non-food before alcohol is counted. Two product pages pinned the mechanism:

| Product | Type | GTIN | Price | `availability` |
|---|---|---|---|---|
| `belbake-bio-dinkel-mehl-vollkorn-bioland/p10079984` | **real grocery** | null | null (`"price":null`) | `InStoreOnly` |
| `silvercrest-brot-frischhaltedose/p100409619` | storage box | 2 GTINs | 9.99 | `OnlineOnly` |

**INFERRED.** Lidl only publishes a price for its `OnlineOnly` range; its actual grocery
range is `InStoreOnly` and returns no price and no GTIN. Resolving a grocery price appears
to require the store-selection flow, which resolves through `/user-api/*` and `/cqe/*` -
**both `Disallow`ed in Lidl's robots.txt, and therefore not probed.** This is a hard stop
under our constraints, not a problem to engineer around.

**VERIFIED - classifier warning.** Slug substrings lie. `silvercrest-brot-frischhaltedose`
contains `brot` but is a bread-freshness *storage container* at 9.99, not bread. Any
grocery classifier built on slug matching must use whole-token matching and will still
need human spot-checks.

**Coverage caveat.** The Lidl store sitemap is uneven: `/filialen/berlin/` exists as a
city page but has **zero** store-detail URLs, while `/filialen/rostock/` has many. The city
index pages, not the sitemap, are the reliable enumeration route.

#### Aldi Nord's advertised sitemap, for comparison

**VERIFIED** (reported from the research session, full analysis pending write-up). Aldi
Nord's sitemap index is `https://www.aldi-nord.de/.aldi-nord-sitemap.xml` with four
children (pages, products, stores, FAQ). Its store URLs are
`/filialen-und-oeffnungszeiten/{city-slug}/{street-slug}/{id}.html` and appear to number in
the low thousands - an order of magnitude below the 21,523 figure in §2.1, which counts
OSM features matching a name filter and is **not** a store count. Critically, **Aldi's
store URLs carry no postcode**; only city, street and a numeric store id. So the Lidl
city-page technique is the thing to try next for Aldi.

### 2.3 Aldi Nord store pages: lat/lng, postcode, hours and banner, all server-rendered

**VERIFIED.** Aldi Nord has no city index page - `/filialen-und-oeffnungszeiten/rostock.html`
returns 404, and `/filialen-und-oeffnungszeiten/rostock/` merely 308-redirects to it. This
is the structural difference from Lidl, whose city pages *are* the enumeration route. For
Aldi, enumeration must come from the advertised store sitemap.

But the individual store page is **richer than Lidl's**. From
`/filialen-und-oeffnungszeiten/rostock/lortzingstrasse-19a/3180621.html` (200, 182 KB), the
`__NEXT_DATA__` payload's `props.pageProps.storeDetail` object yields:

| Field | Observed value |
|---|---|
| `lat` / `lng` | **54.16939 / 12.083483** - exact store position |
| `zip` | **18119** - absent from the sitemap URL, present here |
| `streetAndNumber` | Lortzingstraße 19a |
| `identifier` / `googlePlaceId` | DE029055 / ChIJffEWgSJWrEcRCEkomF2INqg |
| `openingHours` | 7 entries `{dayOfWeek, from1, to1}`; Mon-Thu 07:00-20:00 |
| `specialOpeningHours` | dated closures, e.g. 2026-10-03, 2026-10-31, 2026-12-25/26 |
| `openingHoursNotes` | `Regionalgesellschaft: ALDI GmbH & Co. Kommanditgesellschaft, Jarmen` |
| `services` | Parkplatz, Backstation, barrierefrei, Packstation, … |
| `paymentOptions` | V-Pay, AMEX, GOOGLEPAY, ALDI Geschenkkarte, … |

**INFERRED, and it matters for §5: these are real store coordinates, not postcode
centroids.** Cross-checked against `plz_geocoord`, the Lortzingstraße store sits **0.56 km**
from the 18119 centroid but 2.2-10.9 km from the other Rostock centroids it was compared
against. A German city postcode centroid can be several kilometres from the actual shop, so
centroid-based placement would systematically mis-estimate walking distance. Using true
store positions is a material accuracy gain for exactly the multi-store/pedestrian cases
this project is about (§5.2, §6.2).

**VERIFIED - this closes open question 2 for Aldi Nord.** `openingHoursNotes` names the
operating **Regionalgesellschaft** (the regional legal entity, here ALDI GmbH & Co. KG at
Jarmen). Each store therefore identifies its own banner, and banner-level assortment
modelling is answerable from the locator payload - no additional source, and no need to
treat Aldi as a single uniform chain.

**VERIFIED - negative finding.** The page has 8 `application/ld+json` blocks but **none** is
a `Store`/`LocalBusiness` entity. The address and hours are *not* available as schema.org
markup; they live only inside the Next.js payload. So a generic "harvest schema.org from
retailer sites" strategy would find nothing on Aldi Nord.

### Net effect on open questions 1 and 2

| Chain | Store locator | Postcode | Coordinates | Opening hours | Banner |
|---|---|---|---|---|---|
| **Lidl** | city pages, 3,669 sitemap URLs | yes (aria-label) | no | no | no |
| **Aldi Nord** | store sitemap + detail pages | yes (`zip`) | **yes, exact** | **yes, + closures** | **yes** |

Question 1 ("do the six chains publish machine-readable store locators?") is now **answered
yes for 2 of 6**, and neither chain needs an external gazetteer. Question 2 (per-banner
assortments) is **answered for Aldi Nord**.

The honest summary: **store locators are essentially solved for the two reachable chains,
and prices remain the binding constraint at 1 of 6** - where the Lidl result shows the wall
is *data availability*, not scraping difficulty. That reframes the risk: the project is not
at risk of failing to collect Aldi data, it is at risk of having nothing to optimise
across.

**UNKNOWN.** Aldi Nord, Lidl, Netto and REWE each operate **regional banners with
different legal entities and different assortments** (e.g. Aldi Nord vs. Aldi Süd;
Netto Marken-Discount vs. Netto Nord). A store is therefore not identified by chain name
alone. Whether the optimiser must model banner-level assortments is **UNKNOWN** and
materially changes the price-matching problem.

---

## 3. Routing

**Question: can we compute travel time and distance between home and candidate stores,
per transport mode, using free infrastructure?**

This is the most consequential negative finding in the phase.

### 3.1 OSRM's public demo server must not be used

**VERIFIED.** The public OSRM demo server
(`https://router.project-osrm.org/route/v1/{profile}/...`) returned an **identical**
result for `driving`, `cycling` and `foot` on the same origin/destination pair:
**1,175 m / 165 s in all three cases**.

**INFERRED.** Unsupported profiles silently fall back to the car profile rather than
erroring. An implementation that trusted this server would confidently return driving
distances and durations labelled as walking and cycling, and would therefore
overestimate the attractiveness of distant stores for pedestrians and cyclists - the
exact users for whom multi-store trips are most costly. This is a silent-wrong-answer
failure mode, not a visible one.

### 3.2 Valhalla supports the modes we need, but not transit

**VERIFIED.** The public Valhalla instance (`https://valhalla1.openstreetmap.de/route`)
returned clearly distinct results for the same origin/destination pair:

| Requested mode | Distance | Duration |
|---|---|---|
| `auto` | 1.952 km | 6.2 min |
| `bicycle` | 1.149 km | 4.4 min |
| `pedestrian` | 0.980 km | 11.6 min |

The ordering is physically sensible (pedestrian route longest in distance, shortest in
speed), so the modes are genuinely differentiated.

**VERIFIED.** A `multimodal` request failed with
`Locations are in unconnected regions`. The instance self-reports version `3.9.0-685e3d8`
and returns empty `actions`.

**INFERRED.** The public Valhalla instance is configured **without transit data**. Its
mode support therefore covers 3 of the 5 required modes (walk, bike, car) and excludes
public transport.

### 3.3 Public transport needs a different data source entirely

**VERIFIED.** `https://v6.vbb.transport.rest/locations?query=Alexanderplatz` returned
usable JSON stop data with **no API key required**. This is a HAFAS wrapper: the
naming pattern is per-operator (`v6.<operator>.transport.rest`).

**VERIFIED.** A generic `v6.transport.rest` request for Rostock and Berlin returned
non-JSON responses.

**INFERRED.** Transit routing must be built on a HAFAS/GTFS feed and a proper journey
planner (e.g. HAFAS-based engines), or be restricted to a small set of operators with
known working endpoints. It is **not** obtainable from the same routing engine used for
walk/bike/car.

**UNKNOWN.** Which HAFAS operators have current, maintained endpoints on
`transport.rest` for the regions we care about - in particular MV (Mecklenburg-Vorpommern)
for Rostock, and whether VBB coverage extends usefully beyond Berlin. Also **UNKNOWN**:
fare data per journey, which most free transit APIs do not expose at all (see §5.2).

**Recommendation.** Self-host GraphHopper or OSRM/Valhalla for walk/bike/car, and treat
transit as a separate, deliberately-scoped workstream. Do **not** silently degrade an
unsupported mode to a car estimate - the OSRM demo behaviour above shows that this
failure is silent, and the error will surface as bad product advice rather than an
exception.

---

## 4. Energy cost

Two distinct energy questions exist and they are often wrongly conflated: **fuel** for
cars, and **electricity** for EVs.

### 4.1 Fuel

**PUBLISHED (not verified in this session).** tankerkoenig publishes German fuel prices
as open data at `creativecommons.tankerkoenig.de/api/v4`, on a Creative Commons basis,
with a registered API key, and with the documented expectation that consumers do not
mass-harvest it. Historic data is timestamped per station, which is what would make
"which station was cheapest near me" answerable.

**UNKNOWN.** The exact licence version, rate limits, and whether the service is
appropriate for a production dependency at all. The "do not mass-harvest" posture
conflicts with building a product on top of it, and this needs a decision before any
code exists.

**INFERRED.** Real-time fuel price is close to irrelevant to the optimisation problem,
because refuelling is an incidental cost of driving that every car trip incurs
regardless of which store is chosen. It scales with *distance*, not with *which shop*.
So fuel price precision has low marginal value in the ranking of candidate stores.

### 4.2 Electricity - the interesting one is time-varying

**VERIFIED.** SMARD, the Bundesnetzagentur's electricity market data platform, has a
documented OpenAPI specification at `https://smard.api.bund.dev/openapi.yaml`
(HTTP 200). Key facts read from the specification:

* Server: `https://www.smard.de/app`
* Time-series path: `/chart_data/{filter}/{region}/{filterCopy}_{regionCopy}_{resolution}_{timestamp}.json`
* `resolution` enum: `hour`, `quarterhour`, `day`, `week`, `month`, `year`
* `region` enum: `DE`, `AT`, `LU`, `DE-LU`, `DE-AT-LU`, `50Hertz`, `Amprion`, `TenneT`,
  `TransnetBW`, `APG`, `Creos`
* Response schema: `{"meta_data": {...}, "series": [[epoch_millis, value], ...]}`
* Documented 404 meaning: "No data for combination of filter region and resolution or
  mismatch between copy parameters"

**VERIFIED.** The `filter` parameter is a **numeric module ID**, not a descriptive name.
A live day-ahead price request using a guessed `filter=price` returned HTTP 404. The
module ID for the price series was **not resolved** in this session.

**PUBLISHED.** From SMARD's own quarterly articles: average day-ahead price was
**102.17 €/MWh in Q1 2026** (−8.7% year-on-year) and **93.15 €/MWh in Q4 2025**
(−9.2% year-on-year). The record price quoted by SMARD is **656.37 €/MWh**, occurring on
03.09.2024 between 19:00 and 20:00.

**UNKNOWN.** The SMARD data licence. Secondary sources describe SMARD data as CC BY 4.0,
but this was **not confirmed against the source's own terms** and must not be relied on
until it is. This is a licensing question that has to be answered before any EV costing
is built.

**INFERRED - the genuinely interesting result.** The spread between an average of
~102 €/MWh and a peak of ~656 €/MWh is roughly 6×, **within a single day**. If EV charging
is optimisable against day-ahead wholesale prices, then *when* you charge can matter
more to total cost than *which supermarket* you drove to. That is a more interesting
product insight than the basket comparison the project started with, and it is
orthogonal to it: charging optimisation is a separate decision from shopping-trip
optimisation, and the project should not conflate them.

**ASSUMPTION / UNKNOWN.** A retail EV user is normally on a **fixed household tariff**,
not exposed to wholesale day-ahead prices at all. If the target user is on a fixed
tariff, wholesale price data does not help them and the whole EV-energy sub-problem
disappears. This assumption must be an explicit, user-facing input, not a default.

**UNKNOWN.** Household electricity price data, if obtainable from SMARD or elsewhere, and
the network levies/ taxes that dominate the actual bill. Day-ahead wholesale price is a
small fraction of a German retail electricity bill; using it as the cost of charging
without levies would materially understate cost.

---

## 5. Travel cost

**This is the section that changes the project's shape.** Travel cost is not a single
number per mode - it has a **fixed** component and a **marginal** component, and the split
determines whether a second store is worth visiting.

### 5.1 Fuel vs. electricity vs. zero

**VERIFIED / PUBLISHED** for the price inputs (see §4). The *structure* is the part that
matters:

* **Walking, bicycle:** marginal monetary cost = 0. Only time.
* **Car (ICE/diesel):** marginal cost = distance × (1 / consumption) × price_per_litre.
  Depends on live fuel price (§4.1), which is low-value (§4.1 inference).
* **EV:** marginal cost = distance × consumption_kWh_per_km × (retail price, **or** the
  time-varying price *if* the user is on a dynamic tariff). Deps strongly on the tariff
  assumption (see §4.2).

**UNKNOWN.** Parking fees at German supermarket car parks. This is a real, often
non-trivial cost at city-centre REWE/EDEKA/Kaufland/Netto sites and it penalises exactly
the central stores that are otherwise most attractive. No open source identified.

**UNKNOWN.** German vehicle tax (`Kfz-Steuer`) and any low-emission-zone (Umweltzone)
charges, both of which are location-dependent and would need per-store modelling.

### 5.2 Public transport is a fixed cost, and this changes the answer

**VERIFIED.** The Deutschlandticket costs **€63 per month** from 01.01.2026. This is
corroborated by multiple independent sources including MVG, DB Regio
Mecklenburg-Vorpommern, Deutsche Wikipedia and tagesschau.de. Prior prices: €49 from
01.05.2023, €58 from 2025.

**VERIFIED (via search of official and press sources).** From 2027 the price is to be set
by an index incorporating wage and energy costs, with Bund and Länder support capped at
€1.5bn per year each. Press reporting in August 2026 projected €66.40/month from 2027 -
this is a **projection, not a decision**, and should not be hard-coded.

**INFERRED - the important consequence.** If a user already holds a Deutschlandticket,
the **marginal** cost of any additional transit leg is **€0**. Therefore a multi-store
trip costs no more in transit than a single-store trip, and the entire marginal cost of
visiting a second store is the extra basket savings. The optimal trip structure for a
Deutschlandticket holder is completely different from that of a car user, for whom each
additional store adds a real fuel cost.

This means **the optimal answer is a function of the user's transport situation, not
just their postcode.** A single "best place to shop" answer would be actively wrong for
a meaningful share of users. The output must be conditional on mode and on whether
fixed costs are already sunk.

**ASSUMPTION.** If the user does *not* hold a Deutschlandticket, the model needs either
a single-journey ticket price (per Verkehrsverbund, **UNKNOWN** - not identified from any
open source in this phase) or an amortisation rule
(`63 € / expected journeys per month`, where expected journeys is a user input).

**INFERRED.** The fixed/marginal split means the recommender should surface
*conditional* recommendations ("given you have a Deutschlandticket, X; if you drive, Y")
rather than collapsing to one answer. This is cheap to implement and much more honest
than picking one.

---

## 6. The optimisation problem

Written out explicitly, because the point of this section is to show that **the
optimiser is deterministic and does not need ML.**

### 6.1 Single store

For a start point `h`, mode `m`, store `s` and shopping list `L = {(i, q_i)}`:

```
cost_single(h, s, m, L) = Σ_i  q_i · price(i, s)                 # basket
                        + travel_cost(h → s, m)                 # outbound
                        + travel_cost(s → h, m)                 # return
```

### 6.2 Multiple stores

For a partition of the list into `k` non-empty subsets `S_1 … S_k` assigned to stores
`s_1 … s_k`:

```
cost_multi(h, S_1..S_k, s_1..s_k, m) = Σ_j [ Σ_{i ∈ S_j} q_i · price(i, s_j) ]   # baskets
                                      + travel legs in visiting order
```

The leg structure depends on mode: a car or bicycle can chain `h → s_1 → s_2 → … → h`
optimally, whereas for **walking** the visits are effectively a travelling-salesman
problem, and for **transit** a multi-store trip is a single multimodal journey whose cost
is often *not* the sum of the individual legs.

### 6.3 Complexity and the honest engineering consequence

**INFERRED.** General set-partition optimisation is NP-hard. But the practical sizes are
small: a realistic basket is tens of items, and a postcode neighbourhood yields tens of
candidate stores, not thousands. Restricting to `k ≤ 3` stores over a pre-filtered
candidate set is tractable by exhaustive enumeration with branch-and-bound, in
milliseconds. **No heuristic, and certainly no ML, is required.**

**INFERRED - and this is a correctness trap.** Enumerating store *subsets* is easy;
enumerating list *partitions* is what blows up (Bell numbers). The standard wrong
implementation takes, for each subset of stores, the greedy per-item cheapest assignment
and never revisits it. That is a heuristic, not an optimum, and it will produce
suboptimal trips without any error. If the project wants a defensible "cheapest", the
partition search must be exact at the sizes it advertises, or the output must be labelled
as an approximation.

**Recommendation.** Solve exactly for `k = 1` and `k = 2` (cheap, covers the large
majority of real decisions), and treat `k ≥ 3` as explicitly approximate and labelled.

### 6.4 What genuinely cannot be computed

* **Products not stocked** are `price = ∞`, not `price = 0` and not "unknown". A store
  missing half the basket should not appear to be cheap. This distinction is
  load-bearing and is a common implementation error.
* **Unmatched list items** must surface to the user, not be dropped.

---

## 7. Competitive landscape

**This is the most uncomfortable section, and it was the least expected result of the
phase.**

**VERIFIED.** **smhaggle** (smhaggle.com) is a live German shopping app that already
implements the core concept. Per its own Google Play and website listings it offers:

> "Let the smhaggle App calculate the lowest costs for your planned purchase using the
> shopping list." and "Decide whether you want to buy everything from one retailer or
> visit several retailers. The smhaggle | App shows you the respective prices for your
> shopping cart."

It also does location-based store discovery ("use the map to determine your location
and shopping radius"), an EAN scanner, price history and price alerts, cashback via
receipt upload, and monetises through retailer advertising and cashback. Publicly
documented as launching in October 2019.

**INFERRED.** smhaggle already ships multi-store basket optimisation and location
filtering. The Phase 2 concept as originally scoped - "which store(s) should I visit for
this list" with a location - is **not novel**. Any project plan that treats it as novel is
planning something that already exists.

**VERIFIED.** **kaufDA** (Bonial International) is a large incumbent: local weekly ads
and offers for REWE, EDEKA, Kaufland, Netto and many others, shared shopping lists,
price-drop alerts, and nearby-store lookup with opening hours and contact details.

**VERIFIED.** **Schlaukorb** is a newer entrant whose store listing describes itself as
showing offers "from your region" across Lidl, Aldi, REWE, Penny, Netto, Kaufland and
Edeka, and whose key feature is a smart shopping list that is
**"automatically sorted by market - so you buy everything at the cheapest place"**. Public
store metadata indicates a May 2026 release, free, roughly 10k monthly downloads and a
4.4 rating from 38 reviews. **These are third-party estimates, not audited figures.**

**UNKNOWN.** CartList was in scope for this comparison but was **not** verified, and no
claim about it should be made.

**INFERRED - where the actual gap is.** On the evidence gathered, every verified
competitor is optimised for **products and promotions**. **None** of the verified
competitors factor **travel cost** into the recommendation. smhaggle finds the cheapest
*basket*; it does not appear to answer "is driving 4 km to a cheaper Aldi worth it?".

That is the defensible position for this project, and it is narrower than the original
brief: not "cheapest basket near you" but **"cheapest total cost, including the trip"** -
i.e. a genuine multi-objective optimisation over price and travel, with the result
conditional on the user's mode and transport situation.

**INFERRED.** This is also a *narrowing*, not a strengthening. A travel-cost-aware
recommender is only as good as its price data, and Phase 1 established that price data is
the project's weakest link, available for one of six chains. Building a sophisticated
optimiser on a single-chain price feed would be optimising a mostly-unknown function.

---

## 8. ML / NLP - what is actually justified

Reassessed against the reframed problem rather than the original one.

| Component | ML needed? | Reasoning |
|---|---|---|
| Basket arithmetic | **No** | Pure arithmetic |
| Travel cost / routing | **No** | Deterministic engines exist (§3) |
| Store selection, multi-store | **No** | Exact enumeration at realistic sizes (§6.3) |
| Travel-cost vs. price trade-off | **No** | Deterministic multi-objective optimisation |
| **Cross-chain product entity resolution** | **Yes** | Own-brand problem; no GTIN on Aldi Nord (§Phase 1); only ~5.1% overlap in Open Prices |
| **Free-text list → normalised item** | **Yes** | Users type "milch 3,5% 1l"; a parser, not a formula |
| Store→chain identity resolution from OSM | **Possibly** | Name/brand noise; could be rules first, ML if rules fail |
| German sentiment / aspect analysis | **Not yet justified** | Phase 1 found no accessible review data. Building sentiment on absent data is building nothing. |
| EV charging-time optimisation | **No** | Deterministic against a published price series (§4.2) |

**INFERRED.** The reframing **reduces** the honest ML surface rather than expanding it.
Four of the originally proposed components (sentiment, price prediction, demand/availability
prediction, recommendation) are now either unsupported by available data or replaceable by
deterministic methods. The two that remain genuinely ML - entity resolution and list
parsing - were already the strongest candidates in Phase 1.

**Recommendation.** Defer sentiment work until review data with clear licensing actually
exists. Do not build a model to fit a dataset that is not there.

---

## 9. Recommendation

1. **Adopt the total-cost framing**, but state it honestly as a *narrowing* of the goal
   relative to existing competitors, differentiated by travel-cost awareness (§7).
2. **Postcode resolution: use `plz_geocoord` (Apache-2.0) as a pinned static file**, with
   OpenPLZ for administrative validation. Do not geocode on every request.
3. **Branch data: prefer the retailers' own store locators, fall back to Overpass/OSM.**
   Lidl and Aldi Nord both publish machine-readable stores (§2.2-2.3), and Aldi Nord even
   gives exact coordinates and a regional banner. OSM stays valuable for the four chains
   that are blocked. Treat completeness as a reported confidence, not a hidden assumption.
   Do not quote 21,523 as a store count.
4. **Routing: self-host** walk/bike/car. **Do not use the OSRM public demo** - it
   silently returns car results for all profiles (§3.1). Treat transit as a separate
   workstream on HAFAS/GTFS.
5. **Make transport situation an explicit user input**, not a default, because it
   changes the answer (§5.2).
6. **Solve the optimiser exactly for 1-2 stores; label 3+ as approximate** (§6.3).
7. **Keep the data problem front and centre.** The optimiser is the easy part. Aldi Nord
   is the only chain we can price, so the honest first milestone is a *single-chain,
   travel-aware* recommender - and even that is blocked on the open questions below.

### Before any implementation, resolve these

| # | Question | Status |
|---|---|---|
| 1 | Do the six chains publish machine-readable **store locators** on their store-finder paths? | **Answered yes for 2/6.** Lidl: postcodes via city pages. Aldi Nord: postcode + exact lat/lng + hours via store pages (§2.2-2.3). No external gazetteer needed. The other 4 remain 403/challenge-gated. |
| 2 | Per-**banner** (not per-chain) assortments - does the optimiser need them? | **Answered for Aldi Nord.** Each store names its Regionalgesellschaft in `openingHoursNotes` (§2.3). REWE/Netto/Kaufland still open, but all 4 are unreachable anyway. |
| 2a | Are Aldi Nord's **Regionalgesellschaft** regions mappable to *assortment* differences, or do they differ only legally? | **Open.** The entity is identifiable; whether assortment actually varies by region is untested and would need product-catalog comparison across banners. |
| 3 | Is SMARD data licence-compatible with this use? | EV costing |
| 4 | Is tankerkoenig's licence and scale policy acceptable as a dependency? | Car costing |
| 5 | Single-journey PT fares per Verkehrsverbund - any open source? | Transit costing |
| 6 | Parking fee data for German supermarket sites | Car costing accuracy |
| 7 | Which HAFAS operators are current on `transport.rest` for MV and beyond? | Transit routing |
| 8 | CartList's actual feature set | Competitive accuracy |

---

## Appendix A - Requests made in this phase

Not a verified total count; listed for reproducibility and to show boundedness.

| Endpoint | Purpose | Result |
|---|---|---|
| `nominatim.openstreetmap.org` | Resolve 5 test postcodes | OK |
| `overpass-api.de`, `overpass.kumi.systems` | Grocery features: Rostock, Berlin, national | OK / 504 |
| `overpass.openstreetmap.fr` (mirror) | National retry | Empty for DE |
| `router.project-osrm.org` | Profile-support probe | Silent car fallback |
| `valhalla1.openstreetmap.de/route` | auto / bicycle / pedestrian / multimodal | 3 of 4 work |
| `v6.vbb.transport.rest/locations` | HAFAS operator probe (Berlin) | OK, no key |
| `v6.transport.rest` (generic) | HAFAS probe (Rostock, Berlin) | Non-JSON |
| `raw.githubusercontent.com/.../plz_geocoord` | PLZ centroid CSV + LICENSE | Apache-2.0, 8,298 rows |
| `openplzapi.org/de/Localities` | Admin hierarchy | OK |
| `smard.api.bund.dev/openapi.yaml` | SMARD API spec | OK |
| `www.smard.de/app/chart_data/...` | Day-ahead price series | 404 - wrong `filter` module ID |
| Web search | Deutschlandticket pricing, SMARD publications, competitors | See §5.2, §4.2, §7 |
| `www.lidl.de/static/sitemap.xml` | Lidl sitemap index | 200 - product + **stores** + pages + brands |
| `www.lidl.de/p/export/DE/de/product_sitemap.xml.gz` | Lidl product catalog | 200 - 13,337 URLs, ~99% non-food/alcohol |
| `www.lidl.de/s/de-DE/filialen/sitemap.xml` | Lidl store sitemap | 200 - 3,669 store URLs |
| `www.lidl.de/p/belbake-bio-dinkel-mehl-vollkorn-bioland/p10079984` | Grocery price test | 200 - no price, no GTIN, `InStoreOnly` |
| `www.lidl.de/p/silvercrest-brot-frischhaltedose/p100409619` | Price/GTIN positive control | 200 - 9.99 + 2 GTINs, `OnlineOnly` |
| `www.lidl.de/s/de-DE/filialen/rostock/` | Store→postcode extraction test | 200 - 10 stores with exact postcodes |
| `www.aldi-nord.de/filialen-und-oeffnungszeiten/rostock.html` | Aldi city index page probe | 404 - no such route exists |
| `www.aldi-nord.de/filialen-und-oeffnungszeiten/rostock/lortzingstrasse-19a/3180621.html` | Aldi store-detail payload | 200 - lat/lng, zip, hours, Regionalgesellschaft |

## Appendix B - Corrections to prior work

* `data/raw/spike/README.md` and `access_log.json` originally stated 39 requests / 4
  product pages, went stale after the 09:18 follow-up, and were then over-corrected to
  "42 requests / **5** product pages (3 Aldi Nord, 2 Lidl)". That conflated the Aldi-only
  count with the across-chain total. The Lidl sitemap follow-up adds 8 more requests, 2 of
  them product pages. **Correct totals: 53 requests / 7 product pages (5 Aldi Nord,
  2 Lidl) plus 2 store pages.** Fixed in `access_log.json` (`_provenance.note_on_counts` records the
  correction), `data/raw/spike/README.md` and the `timeline.md` 10:12 entry.
* **Lidl is no longer a candidate price source.** Phase 1 left it as "the make-or-break
  for a second chain with GTIN". Tested and resolved: the catalog is ~99% non-food and
  alcohol, and real groceries return `InStoreOnly` with no price and no GTIN. The Phase 1
  note that "Lidl exposes JSON-LD with SKU, GTIN-13 and price" is **true but misleading** -
  it holds only for the `OnlineOnly` non-food range.
* The cross-chain GTIN count is reported as 388 in one place and 389 in another in the
  Phase 1 notes. The difference is a single product and is most likely a filtering
  difference between the price-export join and the product-table join. **Unreconciled**;
  the defensible statement is "approximately 388-389, about 5.1% of German products".
