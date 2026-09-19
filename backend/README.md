# EduMatch backend

An AI-powered professional network for educators. Teachers describe **what** and
**how** they teach; EduMatch combines structured attributes with semantic
embeddings of their teaching style to recommend the colleagues they are most
likely to collaborate well with — and explains every match.

```
                      FastAPI (one service)
                              |
  auth · users · profiles · recommendations · search · resources
        · ratings · connections · messages · embeddings · demo data
                              |
        +---------------------+----------------------+
        |                                            |
  PostgreSQL 16 + pgvector                  Elasticsearch (optional)
  (system of record, HNSW ANN)              (BM25 + kNN + geo_distance)
```

---

## Quick start (Docker)

```bash
cd backend
cp .env.example .env          # optional: everything has a working default
docker compose up --build
```

That starts PostgreSQL with pgvector, runs the migrations and serves the API:

* API docs (Swagger): <http://localhost:8000/docs>
* ReDoc: <http://localhost:8000/redoc>
* Health: <http://localhost:8000/health>

Seed data (~100 s for the full 10 000-teacher set, ~4 s with `--scale 0.1`):

```bash
docker compose exec backend python scripts/generate_demo_data.py
```

### With the Elasticsearch engine

```bash
SEARCH_PROVIDER=elasticsearch docker compose --profile elasticsearch up --build
docker compose exec backend python scripts/reindex_elasticsearch.py
```

`GET /search/engine` reports which engine is live. If Elasticsearch goes down,
search transparently falls back to Postgres (`SEARCH_FALLBACK_TO_POSTGRES=true`).

---

## Quick start (local Python)

Requires Python 3.12+ and a PostgreSQL 16/17 with the `vector` extension
available.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                  # point DATABASE_URL at your database
createdb edumatch                     # if it does not exist yet
alembic upgrade head                  # creates the schema + extensions
python scripts/generate_demo_data.py --scale 0.1
uvicorn app.main:app --reload
```

---

## Project layout

```
backend/
├── app/
│   ├── main.py                 FastAPI app, CORS, health, OpenAPI metadata
│   ├── config.py               Settings from the environment (12-factor)
│   ├── database.py             Async engine/session, pgvector bootstrap
│   ├── taxonomy.py             Controlled vocabularies + compatibility matrix
│   ├── models/                 SQLAlchemy 2.0 models (one file per table group)
│   ├── schemas/                Pydantic v2 request/response models
│   ├── api/                    Routers: auth, users, profiles, recommendations,
│   │                           search, resources, ratings, connections, messages
│   ├── services/               recommendation · embedding · search ·
│   │                           elasticsearch · storage · profile · demo data
│   └── utils/                  auth (JWT/Argon2), geo (haversine), rate limiting
├── migrations/                 Alembic (async)
├── scripts/                    generate_demo_data.py · reindex_elasticsearch.py
│                               benchmark_recommendations.py
├── tests/                      pytest suite (unit + API integration)
├── Dockerfile · docker-compose.yml · requirements.txt · .env.example
```

---

## The recommendation engine

`GET /recommendations` returns the top matches for the authenticated teacher.

```
score = 0.30 · semantic teaching-style similarity   (pgvector cosine)
      + 0.20 · subject / expertise similarity        (soft Jaccard + synonyms)
      + 0.15 · education-level compatibility         (configurable matrix)
      + 0.15 · teaching-level compatibility          (beginner→advanced ladder)
      + 0.10 · geographic proximity                  (haversine distance bands)
      + 0.10 · class-size similarity                 (1 − |a−b| / max(a,b))
```

Every component is normalised to 0–1 and every weight is configurable
(`REC_WEIGHT_SEMANTIC`, `REC_WEIGHT_EXPERTISE`, …); they are re-normalised so
they always sum to 1.

**Expertise matching** canonicalises synonyms (`ML` → `machine_learning`,
`AI` → `artificial_intelligence`) and scores adjacent fields partially, so
`{python, machine_learning, computer_science}` matches
`{python, artificial_intelligence, computer_science}` at ~0.9 rather than 0.6.

**Education matching** uses a symmetric matrix (`high_school ↔ high_school` =
1.0, `↔ university` = 0.3, `↔ elementary` = 0.2), overridable with
`EDUCATION_COMPATIBILITY_JSON`.

**Location matching** uses haversine distance with bands:
`<5 km → 1.0`, `5–20 → 0.8`, `20–50 → 0.5`, `50–200 → 0.2`, `>200 → 0.0`.
Only coarse city-level coordinates are stored (rounded to ~1 km).

### Explanations

Each result carries display-ready `reasons` plus a structured `explanation`
array for a "Why this match?" panel:

```json
{
  "teacher": { "first_name": "Bob", "location_name": "Cambridge, Massachusetts", "...": "..." },
  "match_score": 0.94,
  "reasons": [
    "92% similarity in teaching philosophy (Project Based)",
    "Shared expertise: Computer Science, Python",
    "Same education level: High School",
    "Both teach Beginner and Intermediate learners",
    "5 km away in Cambridge, Massachusetts"
  ],
  "explanation": [
    { "factor": "semantic", "label": "92% similarity in teaching philosophy",
      "score": 0.92, "weight": 0.3, "contribution": 0.276 }
  ]
}
```

`GET /recommendations/{user_id}/explain` gives the same breakdown for any single
educator. `POST /recommendations/{user_id}/feedback` records
`saved | dismissed | connected` for later weight tuning.

### Performance

Embeddings are generated **on write** (profile create/update), never per
request. A request does:

1. one ANN query against the pgvector HNSW index (`REC_CANDIDATE_POOL`, default 300),
2. one structured overlap query so strong attribute matches are never missed,
3. hybrid scoring in Python over that candidate pool only.

Measured on the full demo dataset (10 000 teacher profiles, 50 000 resources)
on an M-series laptop, 25 runs via `scripts/benchmark_recommendations.py`:

| | |
| --- | --- |
| Candidates scored per request | ~440 |
| Mean | **55 ms** |
| Median | 50 ms |
| p95 | 78 ms |

End-to-end over HTTP (`GET /recommendations?limit=5`) that is ~80 ms including
JSON serialisation. Commonly filtered columns (subjects, expertise, levels,
rating, class size, coordinates) all carry indexes; array columns use GIN.

```bash
python scripts/benchmark_recommendations.py --runs 25
```

---

## Embeddings

`EmbeddingService.generate_embedding(text)` is the only entry point. Providers
are selected with `EMBEDDING_PROVIDER`:

| Provider | Notes |
| --- | --- |
| `hashing` (default) | Deterministic local bag-of-n-grams. No API key, reproducible, ideal for demos and tests. |
| `openai` | `text-embedding-3-small` by default; requests `EMBEDDING_DIM` dimensions. |
| `voyage` | `voyage-3-lite` by default. |

A hosted provider with no `EMBEDDING_API_KEY` logs a warning and falls back to
`hashing` rather than failing at boot. The embedded text is
`teaching_style + bio + teaching_methods + fields_of_expertise + subjects +
education_levels`.

Changing `EMBEDDING_DIM` requires a new migration for the `vector(n)` columns
and a re-embed of existing rows.

---

## Search

`GET /search/teachers` supports `query`, `subject`, `education_level`,
`teaching_level`, `teaching_method`, `teaching_style`, `location`,
`latitude`/`longitude`/`radius_km`, `minimum_rating`, `class_size`, `language`,
`institution_type`, `min_years_experience`, `sort`, `limit`, `offset`.

* **postgres** (default): SQL filters, `ts_rank_cd` lexical ranking and pgvector
  cosine similarity combined as `0.7·semantic + 0.3·lexical`; haversine distance
  computed in SQL with a bounding-box pre-filter.
* **elasticsearch**: the same filters as `term`/`range`/`geo_distance` clauses,
  BM25 `multi_match` and a `knn` block over a `dense_vector` field, merged by
  Elasticsearch. Hits are resolved back to Postgres rows so both engines return
  identical payloads.

Documents are synced on every profile/resource write; `scripts/reindex_elasticsearch.py`
rebuilds both indices from scratch.

---

## API surface

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` · `POST /auth/change-password` |
| Users | `GET/PUT/DELETE /users/me` · `GET /users/{id}` |
| Profiles | `POST /profiles` · `GET /profiles/me` · `PUT /profiles/me` · `DELETE /profiles/me` · `GET /profiles/{user_id}` |
| Recommendations | `GET /recommendations` · `GET /recommendations/{user_id}/explain` · `POST /recommendations/{user_id}/feedback` |
| Search | `GET /search/teachers` · `GET /search/resources` · `GET /search/engine` |
| Resources | `POST /resources` · `POST /resources/upload` · `GET /resources` · `GET /resources/recommended` · `GET/PUT/DELETE /resources/{id}` |
| Ratings | `POST/PUT/DELETE /teachers/{id}/ratings` · `GET /teachers/{id}/ratings` · `GET /teachers/{id}/ratings/summary` |
| Connections | `POST /connections` · `GET /connections` · `PUT /connections/{id}` · `DELETE /connections/{id}` |
| Messages | `POST /messages/conversations` · `GET /messages/conversations` · `GET/POST /messages/conversations/{id}/messages` · `POST /messages/conversations/{id}/read` |
| System | `GET /` · `GET /health` |

Uploads accept PDF, PPT/PPTX, DOC/DOCX, TXT, PNG/JPG up to `MAX_UPLOAD_SIZE_MB`
(25 MB by default), validated by extension allow-list, and are stored locally or
in any S3-compatible bucket (`STORAGE_PROVIDER=s3`).

---

## Demo data

```bash
python scripts/generate_demo_data.py              # 10k users, 50k resources,
                                                  # 30k ratings, 20k connections
python scripts/generate_demo_data.py --scale 0.1  # fast laptop dataset
python scripts/generate_demo_data.py --users 500 --resources 0 --no-truncate
```

The generator drops the pgvector HNSW indexes before the bulk load and rebuilds
them once at the end (`--keep-indexes` opts out) — that alone takes the full
dataset from several minutes to ~100 s.

The data is internally consistent: an elementary teacher never gets
"Advanced Quantum Computing", class sizes follow the education level, resource
difficulty matches its level, and the prose bio matches the structured
attributes (which is what makes the embeddings meaningful). Teachers are spread
across Boston, New York, Toronto, Edmonton, San Francisco, Seattle, London,
Dubai, Singapore, Tashkent and Cambridge MA.

Demo accounts — password **`DemoPassword123!`** for all of them:

| Email | Who |
| --- | --- |
| `demo_teacher@example.com` | **Alice** — high school, CS/Python, project-based, Boston |
| `demo_bob@example.com` | **Bob** — high school, CS/Python, project-based, Cambridge (Alice's best match) |
| `demo_carol@example.com` | **Carol** — university, CS/ML, lecture-based, New York |
| `demo_dana@example.com` | **Dana** — high school physics/engineering, hands-on, Boston |

---

## Hackathon Demo

Five minutes, start to finish. (Swap `curl` for <http://localhost:8000/docs> if
you prefer clicking.)

```bash
# 0. Start everything and seed the dataset
docker compose up --build -d
docker compose exec backend python scripts/generate_demo_data.py --scale 0.1

# 1. Log in as Alice (high school CS teacher in Boston)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo_teacher@example.com","password":"DemoPassword123!"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# 2. Her profile is what everything is matched on
curl -s http://localhost:8000/profiles/me -H "Authorization: Bearer $TOKEN"

# 3. THE DEMO: recommendations, with reasons
curl -s "http://localhost:8000/recommendations?limit=5" -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool

# 4. "Why this match?" for the top result
BOB=$(curl -s "http://localhost:8000/recommendations?limit=1" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["teacher"]["user_id"])')
curl -s "http://localhost:8000/recommendations/$BOB/explain" -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool

# 5. Find one of his resources
curl -s "http://localhost:8000/resources?owner_id=$BOB&limit=3" | python3 -m json.tool

# 6. Connect with him
curl -s -X POST http://localhost:8000/connections -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"receiver_id\":\"$BOB\"}"

# 7. …and say hello
curl -s -X POST http://localhost:8000/messages/conversations -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"participant_id\":\"$BOB\",\"content\":\"Loved your project-based Python unit - want to co-build one?\"}"
```

**What the judge sees at step 3:** Bob (high school, computer science, Python,
project-based, 8 km away) ranks first with a match score above 0.9, ahead of
Carol who teaches the same subject at university level in a different city with
a lecture-based style. The `reasons` array spells out exactly why — shared
subjects, same education level, similar class size, distance, and the percentage
similarity of their teaching philosophies.

Want the same thing through search instead? Try:

```bash
curl -s "http://localhost:8000/search/teachers?query=students%20build%20real%20software%20in%20teams&latitude=42.36&longitude=-71.06&radius_km=50" \
  | python3 -m json.tool
```

---

## Tests

```bash
pytest                      # everything
pytest -m "not integration" # unit tests only (no database needed)
```

API tests need PostgreSQL with pgvector; set `TEST_DATABASE_URL` (defaults to
your `DATABASE_URL` with a `_test` suffix). If the database is unreachable the
integration tests **skip** with an explanatory message instead of failing.

Covered: registration, login, profile creation/updates, recommendation
calculation (including *Teacher A must rank Teacher B highly when their profiles
are similar*), semantic similarity, location similarity, search filters,
resource creation/upload/ownership, ratings and rollups, connections, messaging,
authorisation on every protected route, and the demo data generator.

---

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://edumatch:edumatch@localhost:5432/edumatch` | Async Postgres DSN |
| `JWT_SECRET` | *(change it)* | HS256 signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token lifetime |
| `EMBEDDING_PROVIDER` | `hashing` | `hashing` · `openai` · `voyage` |
| `EMBEDDING_API_KEY` | — | Required by hosted providers |
| `EMBEDDING_DIM` | `384` | Vector width (schema-affecting) |
| `SEARCH_PROVIDER` | `postgres` | `postgres` · `elasticsearch` |
| `ELASTICSEARCH_URL` | `http://localhost:9200` | Cluster endpoint |
| `STORAGE_PROVIDER` | `local` | `local` · `s3` |
| `MAX_UPLOAD_SIZE_MB` | `25` | Upload ceiling |
| `CORS_ORIGINS` | `*` | Comma-separated origins |
| `RATE_LIMIT_PER_MINUTE` / `AUTH_RATE_LIMIT_PER_MINUTE` | `120` / `20` | Per-IP limits |
| `REC_WEIGHT_*` | see above | Recommendation weights |
| `REC_CANDIDATE_POOL` | `300` | ANN candidates scored per request |

Full list with comments: [`.env.example`](.env.example). Secrets come from the
environment only — nothing sensitive is committed.

---

## Security

* Passwords hashed with **Argon2id**; `password_hash` is never returned by any
  endpoint and login errors are identical for unknown user and wrong password.
* JWT bearer auth with dependency-injected `get_current_user`; every write path
  checks ownership (resources, ratings, connections, conversations).
* Pydantic v2 validation on every payload; uploads validated by extension
  allow-list and size limit; SQLAlchemy parameter binding throughout (no string
  SQL built from user input).
* Per-IP sliding-window rate limiting, stricter on `/auth` (swap in Redis for
  multi-worker deployments).
* CORS configured from the environment; run behind HTTPS in deployment.
* Locations are stored at ~1 km precision — city-level only, never street
  addresses.

**Messaging is not end-to-end encrypted.** Messages are protected by HTTPS in
transit and stored server-side so they can be delivered; the API does not claim
otherwise.
