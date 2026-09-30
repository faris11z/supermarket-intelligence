# Supermarket Intelligence

## Project Goal

Build a data-driven shopping-cost optimisation system for Germany covering:

- Lidl
- Aldi
- Kaufland
- Netto
- REWE
- EDEKA

The core question is:

> Given a postcode, a shopping list with quantities, and a transport mode, what is the
> cheapest way to buy everything - and does travelling to a second store pay for itself?

This is a **total shopping cost** question, not a price question. The basket subtotal is
only one term; the trip itself is the other.

---

# Core Concept

The system is NOT simply a price comparison website.

It moves from:

Product → Cheapest supermarket

through:

Shopping List → Basket comparison → Price + customer sentiment + signals

to:

Postcode + List + Mode → Basket + Travel cost + Transport/energy cost
→ Cheapest total cost → Single-store vs. multi-store decision

## What makes the final step different

Price-only comparison answers "where is this basket cheapest", which existing services
already do. The differentiator is **travel-aware total cost**:

- Is driving 4 km to a cheaper Aldi actually cheaper once fuel is counted?
- A Deutschlandticket holder pays **€0 marginal** for any extra transit leg, so their
  optimal trip structure differs fundamentally from a car user's.
- Therefore the answer is **conditional on the user's transport situation**, and a single
  "best shop" answer would be wrong for a large share of users.

The honest position, established in
[`docs/research/location-and-travel-feasibility.md`](docs/research/location-and-travel-feasibility.md),
is that this is a **narrowing and differentiation** of the original goal, not a broader
ambition - see "Competitive reality" below.

## Competitive reality (must not be ignored)

Verified competitors (smhaggle, kaufDA, Schlaukorb) already do location-based
multi-store basket optimisation, offers, lists and price alerts. None of the verified
ones factor **travel cost** into the recommendation.

So the defensible claim is narrow:

> Not "cheapest basket near you" but **"cheapest total cost, including the trip"**.

---

# Development Philosophy

Follow this order:

Data feasibility
→ Data engineering
→ Baseline
→ ML/NLP
→ MLOps
→ Application
→ Deployment

Do NOT introduce ML where a deterministic algorithm is sufficient.

Do NOT build the complete application before validating the data.

Do NOT fabricate missing data.

Clearly distinguish real data, test data and synthetic data.

**Every location-derived distance is an estimate** (a postcode centroid, not the user's
position) and must be labelled as one in output.

**Never silently degrade an unsupported transport mode into a car estimate.** The public
OSRM demo server does exactly this and returns identical car routes for foot and bike
profiles - a failure mode that surfaces as bad advice rather than as an error.

---

# Phase 1 - Research & Data Feasibility

Objectives:

1. Investigate publicly available datasets.
2. Investigate Open Food Facts and Open Prices.
3. Investigate German open-data sources.
4. Investigate available supermarket price/offer data.
5. Investigate review/sentiment datasets.
6. Determine coverage for all six supermarket chains.
7. Investigate historical data availability.
8. Investigate update frequency.
9. Investigate licensing and terms of use.
10. Study existing supermarket comparison services and Idealo.

Deliverable:

A documented data feasibility report.

The report should answer:

- What data can we actually obtain?
- From which sources?
- How much data exists?
- Which supermarkets are covered?
- What fields are available?
- How frequently can data be updated?
- What are the licensing constraints?
- What data is missing?

Do not implement the final pipeline yet.

---

# Phase 2 - Data Architecture

Based on Phase 1, design the data model.

Potential entities:

- Store
- Product
- Category
- Price
- Offer
- Review
- Sentiment
- Availability
- PriceHistory

Design:

- database schema
- raw data structure
- processed data structure
- product identification/matching strategy
- supermarket identification
- historical data representation

Do not assume all supermarkets provide identical data.

---

# Phase 3 - Data Pipeline

Build the first ingestion pipeline.

Pipeline:

Source
→ ingestion
→ raw data
→ validation
→ cleaning
→ normalization
→ processed data
→ database

Requirements:

- reproducible
- testable
- logging
- error handling
- data validation

Keep raw data separate from processed data.

---

# Phase 4 - Exploratory Data Analysis

Analyse:

- number of products
- supermarket coverage
- categories
- price distributions
- missing values
- duplicate products
- product matching
- historical price behaviour
- offers

Create visualizations and document findings.

---

# Phase 5 - Baseline Price Engine

Before ML, build a deterministic baseline.

Input:

Example shopping list:

- Milk
- Eggs
- Chicken
- Rice
- Tomatoes
- Yogurt

Process:

1. Match products.
2. Retrieve prices.
3. Calculate basket cost for each supermarket.
4. Compare individual products.
5. Compare total baskets.

Output:

```text
Supermarket | Basket Cost
Lidl         | €XX.XX
Aldi         | €XX.XX
Kaufland     | €XX.XX
Netto        | €XX.XX
REWE         | €XX.XX
EDEKA        | €XX.XX


Potential aspects:

Price
Quality
Availability
Selection
Service
Store experience
Price Analysis

Price comparison itself does not necessarily require ML.

Use standard programming/data analysis to calculate basket prices.

ML should only be introduced where it provides a genuine benefit, such as:

Sentiment classification
Price/offer prediction
Demand or availability prediction
Other justified predictive tasks

Avoid using ML unnecessarily.

6. Initial Baseline

Before building complex ML models, implement a simple baseline:

Shopping List
      ↓
Match Products
      ↓
Retrieve Prices
      ↓
Calculate Basket Cost
      ↓
Compare Supermarkets

This baseline should work without ML.

It will provide a reference point for evaluating later ML components.

7. MLOps

Potential technologies:

Python
Pandas / Polars
scikit-learn
Hugging Face Transformers
MLflow
DVC
Docker
PostgreSQL
FastAPI
GitHub Actions
pytest

Do not add dependencies until they are justified by the implementation.

Potential MLOps capabilities:

Dataset versioning
Experiment tracking
Model versioning
Automated testing
Model evaluation
Data validation
Data/model monitoring
CI/CD
Reproducible training
8. High-Level Architecture
             Public Data Sources
                     |
                     v
              Data Ingestion
                     |
                     v
             Data Validation
                     |
                     v
              Data Processing
                     |
             +-------+-------+
             |               |
             v               v
       Price Analysis    NLP Pipeline
             |               |
             |        Sentiment Model
             |               |
             +-------+-------+
                     |
                     v
             Comparison Engine
                     |
                     v
             Recommendation
                     |
                     v
                  FastAPI
                     |
                     v
                Web Interface
9. Development Phases
Phase 1 - Data Feasibility

Research available public datasets and APIs.

Determine:

What data exists?
Which supermarkets are covered?
How much data exists?
How current is it?
What can legally be used?
Can the data be updated automatically?

Do not build the final architecture until this analysis is complete.

Phase 1B - Location & Travel Feasibility (**completed**)

Establish whether the total-cost question is answerable from open data: postcode
resolution, branch locations, per-mode routing, transport costs, energy costs, and the
shape of the optimisation problem.

Deliverable:
[`docs/research/location-and-travel-feasibility.md`](docs/research/location-and-travel-feasibility.md)

Findings that constrain all later phases:

- Postcode resolution is solved (Apache-2.0 static file, 8,298 rows).
- Branch data is available from OSM but **imperfect**; completeness must be reported.
- Routing must be **self-hosted**; the OSRM public demo silently returns car routes for
  every profile. Public transit requires a separate HAFAS/GTFS workstream.
- The optimiser is **deterministic** and tractable exactly at 1-2 stores.
- Travel cost has a **fixed** component (Deutschlandticket €63/month since 2026) that
  inverts the optimal trip structure, so transport situation must be a user input.
- The core concept already exists in the market; the differentiator is travel awareness,
  and the price data needed to make it work is the project's weakest link.

Phase 2 - Data Pipeline

Implement ingestion, cleaning, normalization and storage.

Phase 3 - Exploratory Data Analysis

Analyse:

Price distributions
Product coverage
Supermarket coverage
Categories
Missing data
Historical trends
Phase 4 - Baseline

Implement non-ML basket price comparison.

Phase 5 - NLP

Implement and evaluate German sentiment analysis.

Investigate aspect-based sentiment analysis.

> Deferred. Phase 1 found no accessible review data with clear licensing. Do not build a
> sentiment model to fit a dataset that does not exist.

Phase 6 - ML

Add predictive components only where justified by the data.

> Per the Phase 2 reassessment, the honest ML surface is **small**:
> cross-chain product entity resolution, and free-text list → normalised item.
> Everything else (basket arithmetic, routing, store selection, travel/price trade-off)
> is deterministic.

Phase 7 - MLOps

Add:

DVC
MLflow
testing
CI/CD
monitoring
reproducible training

Use only the tools that provide value.

Phase 8 - Application

Build API and web interface.

Phase 9 - Deployment

Deploy the application and document the complete system.

10. Important Engineering Principles
Data availability comes before model selection.
Start with a simple baseline.
Do not use ML where deterministic methods are sufficient.
Every model should have a measurable evaluation metric.
Keep raw and processed data separate.
Track datasets and models.
Make experiments reproducible.
Document data sources and licensing.
Do not fabricate missing supermarket data.
Clearly distinguish real data from synthetic/test data.
Report data-source imperfection instead of hiding it.
Never silently substitute a different transport mode, store, or product than the one requested.
A recommendation must be reproducible: given the same inputs, the same answer.

---

# 11. Success Criteria

The project should eventually be able to:

- Ingest supermarket data.
- Normalize products across different supermarkets.
- Compare prices for equivalent products.
- Calculate shopping-basket costs.
- Resolve a postcode and identify candidate stores near it, reporting source completeness.
- Compute travel time and distance for walking, bicycle and car (and transit where data allows).
- Compute **total** shopping cost, separating fixed from marginal transport cost.
- Recommend a single store **and** justify a multi-store split, exactly for 1-2 stores.
- Give a **conditional** recommendation that depends on the user's transport mode and
  whether a Deutschlandticket is already held.
- Explain the trade-off: how much basket saving is needed to justify the extra trip.
- Expose results through an API.
- Demonstrate reproducible ML/MLOps workflows.
- Provide a usable interface for shopping-list comparison.

Removed from the original criteria, and why:

- *"Analyse German customer sentiment"* / *"Compare sentiment across
  supermarkets/categories"* - no accessible review data with clear licensing was found.
  A criterion that cannot be met with real data is a criterion for fabrication.