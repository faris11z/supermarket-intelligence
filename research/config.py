"""Central configuration for Phase 3 reproducible research.

Every value here is deliberately explicit. Nothing is inferred at runtime and
nothing is read from environment variables, because a research harness that
silently changes behaviour depending on the machine it runs on is not
reproducible.

The one thing that DOES vary is the User-Agent, which must be honest about who
is making the request. See research/README.md for the policy.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_ROOT = REPO_ROOT / "data" / "research"
RAW_DIR = DATA_ROOT / "raw"
NORMALIZED_DIR = DATA_ROOT / "normalized"
REPORTS_DIR = DATA_ROOT / "reports"

REQUEST_LOG = DATA_ROOT / "request_log.jsonl"

# The Phase 1/2 spike evidence lives elsewhere and must not be overwritten.
SPIKE_DIR = REPO_ROOT / "data" / "raw" / "spike"

ALL_DIRS = (DATA_ROOT, RAW_DIR, NORMALIZED_DIR, REPORTS_DIR)


def utc_now() -> str:
    """ISO-8601 UTC timestamp with a trailing Z, second precision."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs() -> None:
    """Create the data tree if missing. Safe to call repeatedly."""
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# HTTP policy
# --------------------------------------------------------------------------

# Honest identification. This is a research harness, not a production crawler,
# and it says so. Do not replace this with a browser string: impersonating a
# browser is explicitly out of scope for this project (see research/README.md).
USER_AGENT = "supermarket-intelligence-research/0.1 (personal feasibility research; bounded requests; contact via repo)"

# Politeness. A delay between requests is the minimum we consider acceptable for
# a research harness hitting third-party infrastructure.
REQUEST_DELAY_SECONDS = 3.0
TIMEOUT_SECONDS = 20

# Hard ceiling per run. The harness refuses to exceed this. A previous phase
# totalled 67 requests manually; a full Phase 3 run should stay in the same
# order of magnitude. Exceeding the cap is a bug, not a discovery.
MAX_REQUESTS_PER_RUN = 120

# --------------------------------------------------------------------------
# Evidence retention
# --------------------------------------------------------------------------

# Bodies are only persisted when they are small AND text-ish. Anything larger
# than this keeps only its sha256, so the log stays auditable without the repo
# quietly filling up with copyrighted retailer HTML.
MAX_INLINE_BODY_BYTES = 2_000_000

# Hard ceiling on what the client will read off the socket. This is a separate,
# stricter limit than MAX_INLINE_BODY_BYTES on purpose: previously the size test
# happened *after* the whole body had been downloaded into memory, so "we only
# store small bodies" did not actually mean "we only download small bodies".
# Anything above this is abandoned mid-stream and recorded as truncated.
MAX_DOWNLOAD_BYTES = 8_000_000
READ_CHUNK_BYTES = 64 * 1024

# robots.txt is a hard gate. When a robots.txt is unreachable, silence is NOT
# permission, so the gate fails closed and the URL is skipped.
#
# The exception is documented, narrow and per-source: the open-data services
# below publish a documented API and an explicit licence, and fetching their
# robots.txt would spend a request against a shared public endpoint (Nominatim
# allows one request per second in absolute terms). Their exemption is recorded
# in the report rather than being a silent default.
ROBOTS_EXEMPT_SOURCES = (
    "open_food_facts",
    "open_prices",
    "osm_overpass",
    "plz_geocoord",
    "nominatim",
    "smard",
)

# Filenames must be filesystem-safe. Built from url + timestamp, never from
# arbitrary user input.
SAFE_FILENAME_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)

# --------------------------------------------------------------------------
# Blocked-result classification
# --------------------------------------------------------------------------

# Anything matching these is recorded and NOT retried. The harness has no
# retry policy on purpose: "retry with different characteristics" is exactly the
# behaviour this project has ruled out.
BLOCKED_STATUSES = (401, 403, 407, 429, 451)

# Substrings that indicate an interstitial challenge rather than a plain 403.
BOT_CHALLENGE_MARKERS = (
    "verification required",
    "verifizierung erforderlich",
    "captcha",
    "are you a human",
    "access denied",
    "zugriff verweigert",
    "request unsuccessful",
    "incapsula",
    "akamai",
)

# --------------------------------------------------------------------------
# Phase 3 probe targets
# --------------------------------------------------------------------------

ALDI_ROBOTS = "https://www.aldi-nord.de/robots.txt"
ALDI_SITEMAP_INDEX = "https://www.aldi-nord.de/.aldi-nord-sitemap.xml"

LIDL_ROBOTS = "https://www.lidl.de/robots.txt"
LIDL_SITEMAP_INDEX = "https://www.lidl.de/static/sitemap.xml"

# Legal pages discovered in Lidl's own advertised pages sitemap
# (www.lidl.de/explore/assets/s/pages_de-DE_de.xml.gz, 2085 locs). These are
# linked by the site, not guessed, which is what makes fetching them in-scope.
# The AGB entry is the one that could actually answer the data-reuse question.
LIDL_LEGAL_PAGES = {
    "terms_onlineshop": "https://www.lidl.de/c/allgemeine-geschaeftsbedingungen-onlineshop/s10005181",
    "impressum": "https://www.lidl.de/c/impressum/s10005238",
    "legal_information": "https://www.lidl.de/c/rechtliche-informationen/s10005200",
    "privacy": "https://www.lidl.de/c/datenschutz/s10005389",
    "withdrawal_rights": "https://www.lidl.de/c/widerrufsrecht-onlineshop/s10005170",
}

# The complete set of genuine food SKUs in Lidl's advertised product sitemap,
# established by whole-token classification plus manual review of all 114
# food-token candidates. See docs/research/phase-3-price-data-validation.md.
# Hard-coding this is deliberate: it is an audited list, not a guess, and it
# keeps the probe deterministic.
LIDL_GROCERY_SLUGS = (
    "belbake-bio-dinkel-mehl-vollkorn-bioland",
    "belbake-dinkelmehl-vollkorn",
    "crownfield-bio-knusper-muesli-beeren",
    "crownfield-knusper-weniger-suess-hafer-muesli",
    "grafschafter-brunchmix-broetchen",
)

# Previously sampled in Phase 1/2 and recorded in data/raw/spike/
# aldi_nord_observed.json. Re-checking these is verification of an existing
# finding, not new crawling. These exact URLs were read out of that evidence
# file, not reconstructed from memory.
ALDI_PRIOR_PRODUCT_URLS = (
    "https://www.aldi-nord.de/produkt/frische-milch-9545",
    "https://www.aldi-nord.de/produkt/haehnchenbrustfilet-teilstuecke-8998",
    "https://www.aldi-nord.de/produkt/weizenmehl-510",
    "https://www.aldi-nord.de/produkt/bananen-6151",
    "https://www.aldi-nord.de/produkt/langkorn-reis-5474",
)

ALDI_PRIOR_STORE_URL = (
    "https://www.aldi-nord.de/filialen-und-oeffnungszeiten/"
    "rostock/lortzingstrasse-19a/3180621.html"
)

# A previously derived estimate that Phase 3 must replace with an exact count.
ALDI_PRIOR_STORE_ESTIMATE = 1693

# --------------------------------------------------------------------------
# Alternative open sources
# --------------------------------------------------------------------------

OFF_API = "https://world.openfoodfacts.org/api/v2/search"

# Open Prices exposes a Vue single-page frontend and a Django REST backend. No
# API path was found reachable in Phase 3; all four candidates below returned
# 404. They are kept here so the negative result is reproducible rather than
# anecdotal, and so a future run can detect if the endpoint ever appears.
OPEN_PRICES_CANDIDATE_URLS = (
    "https://prices.openfoodfacts.org/api/v1/price-list?limit=2",
    "https://prices.openfoodfacts.org/api/v1/prices?limit=2",
    "https://prices.openfoodfacts.org/api/v1/price/?limit=2",
    "https://prices.openfoodfacts.org/api/v1/prices/?limit=2",
)

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# The repository's default branch is `master`, not `main`. Verified by listing
# the repo root through the GitHub contents API on 2026-09-30.
PLZ_GEOCOORD_REPO_API = (
    "https://api.github.com/repos/WZBSocialScienceCenter/plz_geocoord/contents/"
)
PLZ_GEOCOORD_RAW = (
    "https://raw.githubusercontent.com/WZBSocialScienceCenter/"
    "plz_geocoord/master/plz_geocoord.csv"
)
SMARD_SPEC = "https://smard.api.bund.dev/openapi.yaml"

# Chain filter used for the Overpass probe. Mirrors the six target chains.
TARGET_CHAINS = ("lidl", "aldi", "kaufland", "netto", "rewe", "edeka")
