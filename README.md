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
| Aldi Nord prices | Working, full detail including discounts and per-kg prices |
| Lidl, Kaufland, REWE, EDEKA, Netto prices | **Blocked** (403s and bot checks). Lidl reachable but its public catalog is 99% non-food and its grocery prices need robots-disallowed endpoints. |
| Store locations | Solved for 2 of 6 chains, with exact GPS coordinates from Aldi Nord |
| Postcode to coordinates | Solved (Apache-2.0, 8,298 rows) |
| Travel routing | Requires self-hosting; public OSRM demo silently returns car routes for foot and bike |
| Product matching across chains | Unsolved. Aldi publishes no barcodes. |
| Review / sentiment data | **Dropped.** Nothing openly licensed found. |

53 HTTP requests total so far, all logged. No crawler, no bot-protection bypass.

---

## Read next

**New to the project? Start with [`docs/research/beginner.md`](docs/research/beginner.md).**
It explains everything above in plain language, plus the rules we hold ourselves to.

Then:

- [`PROJECT.md`](PROJECT.md) - the full phase-by-phase plan and engineering principles
- [`docs/research/supermarket-data-acquisition-spike.md`](docs/research/supermarket-data-acquisition-spike.md) - Phase 1, which supermarket prices we can get
- [`docs/research/location-and-travel-feasibility.md`](docs/research/location-and-travel-feasibility.md) - Phase 2, locations, travel costs, optimisation
- [`timeline.md`](timeline.md) - dated log of findings, including our mistakes
- [`data/raw/spike/`](data/raw/spike/) - the raw observations and the full request log

## How we work

- Research the data before building anything on it.
- Never fabricate a missing value. Record it as missing, with a note.
- Never quietly substitute something else for what was asked (a different transport mode,
  a different product). A silent substitution is worse than an error.
- Label every claim: verified, published, inferred, assumption, or unknown.
- Retractions go in the timeline in the open.

## Licence and data rights

Unresolved. Retailer data is readable in places, but robots.txt permission is not a licence.
See the open questions in the Phase 2 report.
