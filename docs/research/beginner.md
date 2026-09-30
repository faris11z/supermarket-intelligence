# Start Here: What This Project Is

**Written for someone joining the project today with no prior context. No code knowledge needed.**

---

## The one-sentence version

We are building a tool that answers one question: **given where you live, what you want to
buy, and how you travel, what is the cheapest way to buy it all?**

Not just the cheapest shopping basket. The cheapest **total**, including the trip.

---

## Why the question changed

The original brief was "compare prices across German supermarkets." Research showed that
problem is largely solved by other companies, and that the data to do it well is mostly not
publicly available. So we changed the question.

- **Before:** Which shop has the cheapest basket?
- **Now:** Which way of shopping costs me the least overall, counting the trip?

Example. Milk is €0.40 cheaper at an Aldi 4 km away. Is that actually cheaper? If you drive,
you burn fuel. If you walk 4 km, you spend an hour. But if you already pay a €63 monthly
train ticket, that extra train ride costs you **nothing extra**, so the far-away shop might
genuinely be the right answer.

**Same shopping list, different answer, depending on the person.** That is what makes this
interesting, and it is the part competitors are not doing.

---

## Where the project actually stands

We are in **research**. We have written reports. There is no application yet, and that is
deliberate.

The rule we follow: **do not build anything until we know the data exists.** Building a
system on data that turns out to be unavailable wastes months.

---

## What we have learned so far, in plain language

### The good news

- **We can read Aldi Nord's prices.** One of the six target chains gives us complete,
  current prices including discounts, per-kilogram prices, and promotion dates.
- **We can find the shops.** Two of the six chains publish a list of their stores that we can
  read programmatically. One of them even gives exact GPS coordinates and opening hours.
- **We can turn a postcode into coordinates** using a free, openly licensed file with 8,298
  German postcodes.
- **Travel costs are computable** for walking, cycling and car, once we host the routing
  service ourselves.

### The hard news

- **Only 1 of 6 chains is readable for prices.** Lidl, Kaufland, REWE, EDEKA and Netto all
  actively block automated access (403 errors or bot checks). This is not a bug in our code,
  it is a deliberate choice by those companies.
- **Lidl is a trap.** Lidl looks like the perfect second source. It publishes clean product
  data with barcodes. But 99% of its public catalog is wine, furniture and T-shirts, not
  groceries. And for the groceries it does list, it shows **no price at all** unless you
  pick a specific shop first, which requires endpoints their robots.txt forbids us to use.
  So Lidl is out, for prices.
- **We cannot match the same product across chains.** Each chain mostly sells its own
  "own-brand" version (Aldi: Milsani, Lidl: Sanchia, EDEKA: Fine Food). Aldi does not publish
  barcodes, so there is no reliable way to prove "these two items are the same thing."
- **The public OSM data for shops is unreliable.** A query returned 21,523 "stores" - that
  number is meaningless as a store count and we have explicitly forbidden ourselves from
  quoting it.

### The surprise good news

- **A Deutschlandticket costs €63 per month** (since January 2026). This means train travel
  has a fixed cost you have already paid, so extra legs are free. It flips the optimal
  strategy compared to driving, and it is why the tool must ask the user about their travel
  situation rather than assume.
- **Shops publish their real GPS coordinates**, not just postcode areas. We found one Aldi is
  0.56 km from its postcode centre but up to 10.9 km from neighbouring postcode centres. If
  we used postcode centres, we would badly misjudge how far people actually walk.

---

## The three rules we hold ourselves to

1. **Never invent data.** If a price is missing, we record "missing" and a note explaining
   why. We never guess or fill in a plausible number.
2. **Never quietly change the question.** If a walking route is unavailable, we do not
   substitute a driving route and present it as walking. We found a public routing service
   that does exactly this, which is why we decided to host our own.
3. **Label how sure we are.** Every claim is tagged as verified (we saw it), published
   (the source says so), inferred (we reasoned it out), assumption (a choice we made), or
   unknown (we could not find out).

---

## How the work is organised

| File | What it holds |
|---|---|
| [`docs/research/beginner.md`](beginner.md) | This file. Start here. |
| [`PROJECT.md`](../../PROJECT.md) | The full plan, phase by phase, and the engineering principles. |
| [`docs/research/supermarket-data-acquisition-spike.md`](supermarket-data-acquisition-spike.md) | Phase 1: which supermarket prices we can actually get, chain by chain. |
| [`docs/research/location-and-travel-feasibility.md`](location-and-travel-feasibility.md) | Phase 2: postcodes, shop locations, travel costs, and the optimisation maths. |
| [`data/raw/spike/`](../../data/raw/spike/) | The actual data we pulled, with a record of every single request we made. |
| [`timeline.md`](../../timeline.md) | A dated log of what was done, what we found, and what we got wrong along the way. |

**The research reports are long and detailed on purpose.** They are the evidence. This file
is the summary. If you only read one thing, read this, then skim the summary tables at the
top of each report.

---

## Rules for anyone adding to this

**If you are collecting data from a website:**

- Read that site's `robots.txt` **first**. It tells you what you are allowed to fetch.
- Only fetch what robots.txt points to, like sitemaps.
- Identify yourself honestly. We use a User-Agent that says who we are and that this is
  research.
- Keep requests small and spaced out. We have made 53 requests in total. We are not building
  a crawler.
- If a site blocks you, **stop and write it down.** Do not try to get around it.
- Log every request in [`data/raw/spike/access_log.json`](../../data/raw/spike/access_log.json).

**If you are writing up findings:**

- Say how sure you are, using the tags above.
- If you retract something, say so in the open. The timeline records our mistakes on purpose.

**If you are tempted to add a dependency or a model:** check whether a straightforward
program would do the same job. We reserve machine learning for the two things that genuinely
need it (matching the same product across chains, and turning typed text into a shopping
list). Arithmetic and routing do not.

---

## What is still open

Honest list of what we do not know yet:

- How to get prices from a second chain. The only unblocked lead is a government wholesale
  energy price API, which is not directly useful.
- Whether a product we can identify in two chains is genuinely the same item.
- Whether Aldi's regional companies (there are several legal entities) actually stock
  different products, or differ only on paper.
- Whether we are legally allowed to reuse retailer data at scale. Robots.txt permission is
  **not** a licence. This is unresolved and matters.

---

## The honest summary

We have good news on locations and travel, and bad news on prices. One of six chains is
readable. The project is not blocked on engineering, it is blocked on **data availability**.

That is a real risk, and it is better to say it out loud now than to discover it after
building a system.

Next decision for the group: do we accept a single-chain tool that works well, or keep
working on a second price source?
