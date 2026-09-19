# hackmit-26

[![CI](https://github.com/ProgrammingPerson/hackmit-26/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ProgrammingPerson/hackmit-26/actions/workflows/ci.yml)

**EduMatch** — an AI-powered professional network for educators, built for
HackMIT 2026.

Teachers describe what and how they teach. EduMatch combines structured
attributes (subjects, education level, class size, location) with semantic
embeddings of their teaching style to recommend the colleagues they are most
likely to collaborate well with — and explains every recommendation.

## Repository

| Path | What it is |
| --- | --- |
| [`backend/`](backend/) | FastAPI + PostgreSQL/pgvector + optional Elasticsearch service. See [backend/README.md](backend/README.md). |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | CI: lint, unit tests, the full suite against pgvector with a coverage gate, migrations, the Elasticsearch engine, and a Docker end-to-end smoke test. |

## Live

| | |
| --- | --- |
| API | <https://edumatch-api-asbp.onrender.com> |
| Docs | <https://edumatch-api-asbp.onrender.com/docs> |
| Demo login | `demo_teacher@example.com` / `DemoPassword123!` |

The free instance sleeps when idle — wake it before demoing:
`curl https://edumatch-api-asbp.onrender.com/health`

## Run it locally

```bash
cd backend
docker compose up --build
docker compose exec backend python scripts/generate_demo_data.py --scale 0.1
open http://localhost:8000/docs
```

Then follow the **Hackathon Demo** section of
[backend/README.md](backend/README.md#hackathon-demo): log in as
`demo_teacher@example.com` / `DemoPassword123!`, call `GET /recommendations`,
and see why each educator was matched.
