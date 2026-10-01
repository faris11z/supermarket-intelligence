# Start Here: What This Project Is

**Written for someone joining today with no prior context. No code knowledge needed.**

---

## The one-sentence version

We want to build a tool that answers one question: **given where you live, what you
want to buy, and how you travel, what is the cheapest way to buy it all?**

Not the cheapest shopping basket. The cheapest **total**, including the trip.

---

## Why the question changed

The original brief was "compare prices across German supermarkets." The research found
two things: other companies already do that reasonably well, and the data needed to do
it properly is mostly not publicly available. So we changed the question.

- **Before:** Which shop has the cheapest basket?
- **Now:** Which way of shopping costs me the least overall, counting the trip?

Here is why that matters. Milk is €0.40 cheaper at an Aldi 4 km away. Is that actually
cheaper? If you drive, you burn fuel. If you walk 4 km, you spend an hour of your life.
But if you already pay a €63 monthly train ticket, that extra train ride costs you
**nothing extra**, so the far-away shop really might be the right answer.

**Same shopping list, different answer, depending on the person.** That is the
interesting part, and it is the part competitors are not doing.

---

## Where the project stands

We are in **research**. We have written reports. There is no application yet, and that
is deliberate.

The rule: **do not build anything until we know the data exists.** Building on data
that turns out to be unavailable wastes months.

---

## What we have learned, in plain language

### The good news

- **We can read Aldi Nord's prices.** One of the six target chains gives us current
  prices, discounts, and promotion dates. It also gives a per-kilogram or per-litre
  price, which is the number that makes fair comparison possible.
- **We can find the shops.** Two of the six chains publish a machine-readable list of
  their stores. One of them publishes exact GPS coordinates and opening hours.
- **We can turn a postcode into coordinates** using a free, openly licensed file
  covering 8,298 German postcodes.
- **Travel costs are computable** for walking, cycling and car, once we host the routing
  service ourselves.

### The hard news

- **Only 1 of 6 chains is readable for prices.** Kaufland, REWE, EDEKA and Netto block
  automated access (403 errors or bot checks). That is a deliberate choice by those
  companies, not a bug in our code. Lidl is a different story, below.
- **Lidl is a trap, and not for the reason we first thought.** We expected a bot wall
  and found something stranger. Of the **13,337** products in Lidl's advertised catalog,
  only **5** are actual groceries. The rest is wine, beer, plants, seeds and furniture.
  Lidl's own grocery brands (Solevita, Hahne, Fresko) are not there at all. And for
  those 5 products it publishes **no price and no barcode**, only "available in store".
  The real prices sit behind endpoints its robots.txt forbids us to call. So Lidl is out
  for prices, and the reason is stronger than "blocked".
- **We cannot prove two records are the same product.** Each chain mostly sells its own
  version of the same thing (Aldi: Milsani, Lidl: Solevita, EDEKA: Fine Food).
  **Neither Aldi nor Lidl publishes a barcode**, so there is no reliable way to prove
  "these two items are the same thing". Guessing by name would sometimes be right and we
  would never know which times. A wrong "cheapest" is worse than no answer at all.
- **The public OpenStreetMap shop data is not a store count.** A query returned 21,523
  "stores", which is meaningless. We have explicitly forbidden ourselves from quoting it.

### The surprise good news

- **A Deutschlandticket costs €63 per month** (since January 2026). Train travel has a
  fixed cost you have already paid, so extra legs are free. It flips the optimal
  strategy compared to driving, and it is why the tool must ask about your travel
  situation rather than assume one.
- **Shops publish real GPS coordinates**, not just postcode centres. One Aldi sits 0.56
  km from its own postcode centre but up to 10.9 km from neighbouring ones. Using
  postcode centres would badly misjudge how far people actually walk.

---

## The mistake worth reading about

We got one finding wrong, in a way worth understanding, because it is the kind of
mistake that quietly deletes a capability.

Phase 1 said Aldi publishes a "per-kilogram price" field. Phase 3's parser said there is
no such field. Both could not be true, so the finding sat unresolved and the project
treated unit-price comparison as impossible.

**Phase 3's parser was wrong.** The field is real, but it is not where the parser
looked: it sits nested inside another object, one level deeper than the code reached.
The parser asked for it, got nothing back, and reported "this field does not exist".

The lesson: **a program that fails to read a field looks exactly like a website that
does not have one.** Those two situations need to be told apart, and the only reliable
way is to check the saved raw response rather than trust the code's own summary. The
raw HTML was archived the whole time, which is the only reason this was catchable at
all. We have since fixed the parser and added a check that compares the parsed numbers
against the raw bytes, so it cannot recur silently.

The same mistake appeared in the Lidl catalog analysis, where substring matching
reported a food share near 1% because the letters `-ba` matched *bananenpflanze*
(banan plant) and `-ei` matched *eiche* (oak). Aldi does publish per-unit prices, and
Lidl's catalog does contain flour. Both corrections are recorded in the timeline.

---

## The three rules we hold ourselves to

1. **Never invent data.** If a price is missing, we record "missing" plus a note
   explaining why. We never guess a plausible-looking number.
2. **Never quietly change the question.** If a walking route is unavailable we do not
   substitute a driving route and present it as walking. We found a public routing
   service that does exactly that, which is why we decided to host our own.
3. **Label how sure we are.** Every claim is tagged **verified** (we saw it),
   **published** (the source says so), **inferred** (we reasoned it out), **assumption**
   (a choice we made), or **unknown** (we could not find out).

---

## How to see the results yourself

Everything below runs offline and makes no network requests. Nothing here retries,
proxies, logs in, or executes JavaScript, so you cannot accidentally turn polite
research into a crawler.

```bash
# 1. The headline answer: is the evidence still consistent?
python research/verify_phase3.py

# 2. Rebuild every report from the saved responses, without touching the internet
python -m research.run_probe --offline

# 3. See what is probeable, and re-derive one source
python -m research.run_probe --list
python -m research.run_probe aldi --offline

# 4. Check the documents against the evidence
python research/check_docs_consistency.py
```

`verify_phase3.py` re-reads the saved responses instead of trusting the written reports,
so if a report drifts away from its own evidence, a check fails. It prints 28 results
and currently passes all 28. **That means the evidence is self-consistent. It does not
mean the sources are usable or licensed** — the decision gate below is the honest
answer.

Reports land in `data/research/reports/` as JSON:

| File | What it answers |
|---|---|
| `aldi.json` | Can we read Aldi prices, and what is missing? |
| `lidl.json` | Why is Lidl not a price source? |
| `alternatives.json` | What did the six open-data sources give us? |
| `run_summary.json` | What happened on the last run, and how many requests? |

`data/research/normalized/aldi_products.json` is the same Aldi data in a flat,
easy-to-read list of products.

---

## How the work is organised

| File | What it holds |
|---|---|
| [`docs/research/beginner.md`](beginner.md) | This file. Start here. |
| [`PROJECT.md`](../../PROJECT.md) | The full plan, phase by phase, and the engineering principles. |
| [`docs/research/supermarket-data-acquisition-spike.md`](supermarket-data-acquisition-spike.md) | Phase 1: which supermarket prices we can actually get, chain by chain. |
| [`docs/research/location-and-travel-feasibility.md`](location-and-travel-feasibility.md) | Phase 2: postcodes, shop locations, travel costs, optimisation maths. |
| [`docs/research/phase-3-price-data-validation.md`](phase-3-price-data-validation.md) | Phase 3: the reproducible price validation, with the corrections. |
| [`data/raw/spike/`](../../data/raw/spike/) | The Phase 1/2 raw data, with a record of every request made. |
| [`data/research/`](../../data/research/) | Phase 3 raw responses, request log, evidence manifest, reports. |
| [`timeline.md`](../../timeline.md) | A dated log of what was done, found, and got wrong. |

**The research reports are long on purpose.** They are the evidence. This file is the
summary. If you read only one thing, read this, then the summary tables at the top of
each report.

---

## Rules for anyone adding to this

**If you are collecting data from a website:**

- Read that site's `robots.txt` **first**. It states what you are allowed to fetch.
- Only fetch what robots.txt points to, such as sitemaps.
- Identify yourself honestly. We use a User-Agent that says who we are and that this is
  research.
- Keep requests small and spaced out. We have made **184 real requests in total** (67 in
  Phase 1/2, 117 in Phase 3) across 53 distinct addresses. We are not building a crawler.
- If a site blocks you, **stop and write it down.** Do not try to get around it.
- Log every request, in `data/raw/spike/access_log.json` or
  `data/research/request_log.jsonl`.

**If you are writing up findings:**

- Say how sure you are, using the tags above.
- If you retract something, say so in the open. The timeline records our mistakes on
  purpose.

**If you are tempted to add a dependency or a model:** check whether a straightforward
program would do the same job. We reserve machine learning for the two things that
genuinely need it (matching the same product across chains, and turning typed text into
a shopping list). Arithmetic and routing do not.

---

## What is still open

Honest list of what we do not know:

- **How to get prices from a second chain.** The only unblocked lead is a government
  wholesale energy price API, which is not directly useful.
- **Whether a product we can identify in two chains is genuinely the same item.**
- **Whether Aldi's regional companies** (there are several legal entities) actually
  stock different products, or differ only on paper.
- **Whether the SMARD and tankerkoenig licences** permit the use we have in mind.
- **What carrying the shopping costs you in effort.** We cost fuel and electricity but
  not the human being. A second shop is not just further away, it is more physically
  demanding, and for some people that matters more than the money. We have not
  researched this at all, and a tool that reports euros while ignoring effort will give
  the wrong answer to those people.
- **Whether we are even allowed to use retailer data.** This is the most important open
  item and it is not a technical question. Aldi Nord publishes no terms of use and no
  Impressum, so there is no document that grants permission. German copyright law gives
  the maker of a database the right to control reuse of it, and with nothing granted the
  default is "all rights reserved". Being allowed to *read* a page is not the same as being
  allowed to *use* the data. This needs a lawyer, not more requests.

---

## The honest summary

Good news on locations and travel. Bad news on prices. One of six chains is readable.
The project is not blocked on engineering. It is blocked on **data availability**.

That is a real risk, and it is better to say it out loud now than to discover it after
building a system.

Two decisions, in order:

1. **Get legal advice on retailer data reuse** before anyone writes an ingestion
   pipeline. It can invalidate the whole approach, and it is the cheapest thing to
   resolve.
2. Then decide whether we accept a single-chain tool that works well, or keep working on
   a second price source.
