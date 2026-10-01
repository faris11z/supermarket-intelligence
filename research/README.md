"""Reproducible research harness for the supermarket-intelligence project.

This package exists so that every claim in `docs/research/` can be re-derived
by someone else, rather than taken on trust. A finding is only as good as the
ability to reproduce it.

## What this is

A small, dependency-light harness that:

* makes one bounded HTTP GET per URL, with an honest User-Agent
* respects `robots.txt` as a hard gate (a disallowed path is never requested)
* never retries, never spoofs, never solves a challenge
* records every request as one JSON line in `data/research/request_log.jsonl`
* stores the response body under a content-addressed name plus its SHA-256
* can re-derive every report from cached bodies without touching the network
* saves findings as JSON so they can be diffed between runs

## What this is not

* Not a crawler. There is no queue, no frontier, no recursion, no concurrency.
* Not a scraper in the bypass sense. A 403 is recorded and the path is dropped.
* Not production ingestion code. Nothing here should be promoted to a pipeline
  without re-reviewing the licensing question, which is unresolved.

## Rules this harness enforces on itself

1. **One request per URL per run.** Re-running makes more requests; the harness
   will not pretend otherwise.
2. **A per-run request cap** (`config.MAX_REQUESTS_PER_RUN`, default 120). The
   Phase 1/2 spike totalled 67 requests. Phase 3 made **117 real requests across
   53 distinct URLs** — a research run needing 10x that is a crawler by another
   name. Note the log file is much longer than 184 records: every `--offline` run
   appends a `replayed: true` line per URL, and those are not requests. Count
   records with `models.is_replay_record()`, not by line count.
3. **A delay between requests** (`config.REQUEST_DELAY_SECONDS`, default 3s).
4. **No credential capture.** `cookies=None` on every request. We log in
   nowhere and store no tokens.
5. **Blocks are loud.** A blocked result carries an explicit `result` value and a
   note naming the evidence. It can never be silently counted as a success.

## Offline replay

`--offline` re-derives reports, normalized records and the summary from bodies
already on disk. It makes **zero** network requests, so it is safe to run
anywhere and it cannot put load on a source. Use it to re-check a parser after
changing it, or to re-derive a report without spending part of the request
budget.

```bash
python -m research.run_probe aldi --offline
```

Replay is not a substitute for a live run. An offline report tells you what the
cached evidence supports, not what the source says today, and the two should not
be conflated.

## Evidence integrity

Three details, all of which exist because the naive version was wrong first:

* **Evidence is content-addressed.** Filenames include a digest of the decoded
  body, so re-fetching a URL cannot overwrite an earlier artefact. An earlier
  version named files after the URL alone, which meant a second request made
  the first request's logged SHA-256 unverifiable. Immutable evidence is worth
  more than a tidy directory.
* **Both hashes are recorded.** `sha256` is the hash of the bytes on the wire;
  `sha256_decoded` is the hash after gzip decoding. Sitemaps are served gzipped
  and are doubly so, so these differ, and knowing which one a claim refers to
  is the difference between a check that works and one that always fails.
* **Deletions are logged.** The request log is append-only, so removing an
  artefact writes an `evidence_retired` tombstone explaining why. A delete that
  is not recorded is indistinguishable from data loss.

`verify_phase3.py` checks the *current* artefact for each evidence path and
reports earlier entries as superseded. It deliberately does not re-check
superseded entries against current files: doing so produces a wall of expected
mismatches, and a check that always fails is a check nobody reads.

## Usage

```bash
# from the repository root
python -m research.run_probe --list
python -m research.run_probe              # all sources
python -m research.run_probe aldi         # one source
python -m research.run_probe aldi --offline  # re-derive from cache, no network
python -m research.run_probe --offline     # every source, from cache
python research/verify_phase3.py          # 28 offline consistency checks
python research/check_docs_consistency.py # stale numbers in the docs
python research/retire_evidence.py <path> --reason "why"
python research/migrate_evidence.py       # re-run the content-addressing migration
```

`verify_phase3.py` reads saved artefacts and prints a report. It does not hit
the network, so it is safe to run anywhere and its output is stable.

Its all-passing result means the **evidence is self-consistent**, not that the
sources are usable or licensed. Those are separate questions, answered in
`docs/research/source-suitability-matrix.md`.

## Layout

| Path | Purpose |
|---|---|
| `config.py` | Every constant and URL, explicit and auditable |
| `http_client.py` | The single-request fetch, classification, evidence capture |
| `models.py` | Dataclasses for records; the request-log contract |
| `probes/common.py` | Request log, robots gate, sitemap parsing, JSON-LD helpers |
| `probes/aldi.py` | Aldi Nord: exact sitemap counts, re-verify prior pages |
| `probes/lidl.py` | Lidl: discovery, deterministic grocery sample, licensing |
| `probes/alternative_sources.py` | Open data fallbacks, each actually tested |
| `run_probe.py` | Entry point |
| `verify_phase3.py` | Offline reproducibility check and decision gate |

## Requirements

Python 3.11+ and `requests`. Nothing else. No database, no framework.

## Adding a probe

1. Add the source's URLs to `config.py`.
2. Write `probes/<name>.py` with a `run(log) -> dict` function.
3. Register it in `run_probe.PROBES`.
4. Respect the robots gate. If a source blocks you, record it and stop.
5. Do not treat an HTTP 200 as proof the endpoint works. Require the content you
   expect. `prices.openfoodfacts.org` returns a Vue HTML shell with 200 for any
   non-API path, so a status-only check reports a working API while handing
   back a single-page app.

Do not add a retry parameter. Do not add a proxy option. Do not add a
JavaScript-rendering option without a written justification, because rendering
is the step that turns a polite research client into something that looks like
an attack, and the licence question (unresolved) sits downstream of it.
