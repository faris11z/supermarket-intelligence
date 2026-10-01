# supermarket-intelligence

Find the cheapest way to buy a shopping list in Germany, counting the trip as well as the
basket.

**Status: research phase. No application yet, by design.**

---

## What it does (planned)

You give it a postcode, a shopping list with quantities, and how you travel (walk, bike,
car, train). It tells you where to buy everything, and whether splitting the shop across two
stores is worth the extra trip.

## Why "total cost" and not "price"

A basket that is €4 cheaper 4 km away is not cheaper if you drove there. But if you already
hold a €63/month train ticket, that extra train ride costs nothing, so the far shop can win.

Existing German comparison tools (smhaggle, kaufDA, Schlaukorb) already optimise the basket.
None of them factor in travel. That is the gap this project is aimed at.

## Current state, honestly

| Area | Status |
|---|---|
| Aldi Nord prices | **Working, 4 of 4 sampled pages parsed.** Shelf prices, promotion prices, and Aldi's own per-unit `basePrice` (e.g. 11.32 EUR/kg). The Phase 3 parser initially missed `basePrice` because it read one dict level too shallow; fixed, and the verifier now cross-checks it against the raw HTML. |
| Lidl prices | **Ruled out, not blocked.** Its advertised catalog is 13,337 URLs of which **5** are genuine food (the rest alcohol, plants, non-food). All 5 publish `InStoreOnly` with no price. Its real prices sit behind robots-disallowed endpoints. |
| Kaufland, REWE, EDEKA, Netto prices | **Blocked** (403s and bot checks) as measured in Phase 1/2. |
| Store locations | Solved for 2 of 6 chains, with exact GPS coordinates from Aldi Nord |
| Postcode to coordinates | Solved (Apache-2.0, 8,298 rows) |
| Travel routing | Requires self-hosting; public OSRM demo silently returns car routes for foot and bike |
| Product matching across chains | Unsolved, and now shown to be structural: **neither Aldi nor Lidl publishes a GTIN** on permitted pages. |
| Review / sentiment data | **Dropped.** Nothing openly licensed found. |

No crawler, no bot-protection bypass, no retry logic, no proxies, no headless browser.

---

## Read next

**New to the project? Start with [`docs/research/beginner.md`](docs/research/beginner.md).**
It explains everything above in plain language, plus the rules we hold ourselves to.

Then:

- [`PROJECT.md`](PROJECT.md) - the full phase-by-phase plan and engineering principles
- [`docs/research/supermarket-data-acquisition-spike.md`](docs/research/supermarket-data-acquisition-spike.md) - Phase 1, which supermarket prices we can get
- [`docs/research/location-and-travel-feasibility.md`](docs/research/location-and-travel-feasibility.md) - Phase 2, locations, travel costs, optimisation
- [`docs/research/phase-3-price-data-validation.md`](docs/research/phase-3-price-data-validation.md) - Phase 3, reproducible price and licensing validation
- [`docs/research/source-suitability-matrix.md`](docs/research/source-suitability-matrix.md) - the decision table
- [`timeline.md`](timeline.md) - dated log of findings, including our mistakes
- [`data/research/`](data/research/) - Phase 3 raw evidence, request log, reports
- [`data/raw/spike/`](data/raw/spike/) - the Phase 1/2 raw observations

## Reproduce our own work

```bash
python -m research.run_probe --list        # what can be checked
python -m research.run_probe aldi --offline  # re-derive a report from cached evidence
python -m research.run_probe --offline       # re-derive every report, no network
python research/verify_phase3.py           # 28 offline consistency checks
python research/check_docs_consistency.py  # catch stale numbers in these docs
```

`--offline` makes no network requests. Nothing in the harness retries, proxies,
logs in, or renders JavaScript, so re-running it cannot turn polite research
into a load test.

## How we work

- Research the data before building anything on it.
- Never fabricate a missing value. Record it as missing, with a note.
- Never quietly substitute something else for what was asked (a different transport mode,
  a different product). A silent substitution is worse than an error.
- Label every claim: verified, published, inferred, assumption, or unknown.
- Retractions go in the timeline in the open.

## Licence and data rights

**Unresolved, and the highest-priority open item.** Nothing found so far grants
reuse, and nothing found so far prohibits it either. Under German copyright law
(UrhG §87b) database reuse is reserved to the database maker by default, and
robots.txt permission is a crawl instruction, not a licence.

Phase 3 closed the Lidl half of this question. Its advertised pages sitemap
contains five retrievable legal documents, and the Online-shop AGB
(27.7 KB) is consumer purchase terms with **no clause on automated extraction
or data reuse**, in either direction. Aldi Nord publishes no general terms of
use and no Impressum, so there is no document granting permission and none to
seek it in. Absence of a prohibition is not permission.

Until this is resolved with actual legal advice, the working position is: prototype on
locally cached observations in this repo, no redistribution of retailer data, no production
ingestion pipeline. See section 2.4 of the Phase 2 report and
[`docs/research/phase-3-price-data-validation.md`](docs/research/phase-3-price-data-validation.md).

**117 real HTTP requests** were made in Phase 3, across **53 distinct URLs**, all
logged in `data/research/request_log.jsonl` with status, bytes, and SHA-256.
Phase 1/2 made 67 more, tracked separately in `data/raw/spike/access_log.json`.

The log file is longer than 184 lines, and that is not a contradiction: an
`--offline` run appends one *replay* record per URL it re-reads, and those
records are flagged `replayed: true`. Only the 117 unmarked records are requests
to a server. An earlier version of this file said "235 HTTP requests so far",
which had counted replays as real traffic.

Run `python research/verify_phase3.py` for the current split; it prints the exact
real/replay/tombstone counts every time, so this paragraph cannot silently rot
into a new wrong number.
