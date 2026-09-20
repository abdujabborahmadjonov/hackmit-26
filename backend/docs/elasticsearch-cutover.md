# Switching search from Postgres to Elasticsearch

Postgres stays the system of record either way. Elasticsearch is only a query
engine, so nothing is lost by switching, and rolling back is one env var.

## Where this actually stands

- The Elastic Cloud cluster **exists and is reachable** (~0.14 s from a laptop).
- `SEARCH_PROVIDER` now defaults to `elasticsearch` (changed in PR #17).
- `ELASTICSEARCH_URL` is set in `backend/.env`.
- **`ELASTICSEARCH_API_KEY` is not set**, so the cluster answers every request
  with `401 security_exception: missing authentication`.
- The indices have therefore never been built.

So search is running on Postgres right now, by way of the fallback, even
though the provider says `elasticsearch`. That is the one thing to understand
before touching any of it.

## Why nothing is on fire

Two guards, both added in PR #17, make the broken state degrade quietly:

- Interactive search uses `request_timeout: 3, max_retries: 0`, so a bad
  cluster fails fast instead of hanging the Discover page. The observed cost of
  the 401 is ~0.14 s per search, not 3 s.
- An empty index no longer reads as "a successful search of an empty corpus";
  it falls back to Postgres. This is what protects you between flipping the
  provider and finishing a reindex.

This is also why you cannot tell it is broken by looking at the app.

## How to tell which engine is really serving

Two checks, answering different questions.

```bash
curl -s https://edumatch-api-asbp.onrender.com/search/engine
```

reports what is *configured*, plus a live ping. Whereas every search response
carries an `engine` field reporting what *actually served that query*:

```bash
curl -s 'https://edumatch-api-asbp.onrender.com/search/teachers?q=math&limit=1' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['engine'])"
```

Trust the second. If `/search/engine` says `elasticsearch` but a response says
`engine: postgres`, the fallback is firing.

Baseline on Postgres, for comparison afterwards:
`engine: postgres`, `took_ms: 22.3`, `total: 1000`.

## Finishing the cutover

**1. Put the API key where it is missing.** It needs to be in two places, and
you add both yourself:

- `backend/.env` as `ELASTICSEARCH_API_KEY=...` — open it with
  `open -e backend/.env`. This is what lets you run step 2.
- Render, on the `edumatch-api` service, same variable name. This is what
  makes production use it.

The key needs write access to the `edumatch_*` indices, not just read.

**2. Build the indices.**

```bash
cd backend && .venv/bin/python scripts/reindex_elasticsearch.py
```

It writes to staging indices and only aliases the live names over once the
bulk load succeeds, so a failure leaves search untouched. Expect roughly
"Done: 1000 teachers, 5000 resources".

This reads the **production** database, since that is what `backend/.env`
points at. It only reads.

**3. Verify** with the second curl above. You want `engine: elasticsearch` in
an actual search response, not just in `/search/engine`.

Order matters: the key before the reindex, the reindex before you trust the
provider. Doing step 2 first just reproduces the 401.

## If it goes wrong

Set `SEARCH_PROVIDER=postgres` in Render. That is the whole rollback —
Postgres never stopped being the system of record and its indexes were never
dropped.

Leave `SEARCH_FALLBACK_TO_POSTGRES=true` for the demo: a flaky conference
network then degrades to slower search rather than a 5xx on stage. The cost is
that a silent failure looks like success, which is exactly what the `engine`
field is there to expose.

## Keeping it current

Writes are mirrored as they happen: creating or editing a resource calls
`es.index_resource`, editing a profile calls `es.index_teacher`, and deleting
one calls `es.delete_resource`. The indices do not drift during normal use, so
there is no cron job to run.

Re-run the reindex script after anything that writes to Postgres behind the
app's back — a schema change, or a bulk load such as
`scripts/generate_demo_data.py`.
