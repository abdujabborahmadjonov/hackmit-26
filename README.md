# hackmit-26

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
