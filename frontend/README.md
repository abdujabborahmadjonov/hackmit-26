# EduMatch — frontend

React + TypeScript + Vite client for the [EduMatch API](../backend/README.md).
The whole app is built around one question: *why* is this the right educator to
collaborate with?

**Live:** <https://edumatch-web.onrender.com> — talking to
<https://edumatch-api-asbp.onrender.com>.

## Run it

```bash
cd frontend
npm install
cp .env.example .env     # points at the deployed API by default
npm run dev              # http://localhost:5173
```

Sign in with **“Sign in as Alice (demo account)”** — no typing needed.

To develop against a local backend instead:

```bash
echo "VITE_API_URL=http://localhost:8000" > .env
```

## What's here

| Route | What it does |
| --- | --- |
| `/login`, `/register` | JWT auth; the token lives in `localStorage` |
| `/profile` | Onboarding + editing. Teaching style and bio drive the semantic half of matching |
| `/` | **Matches** — ranked educators, each with plain-language reasons and a "Why this match?" breakdown |
| `/search` | Structured filters + semantic free text + geographic radius |
| `/teachers/:id` | Full profile, the match explanation, their resources, reviews, connect/message |
| `/resources` | "Picked for you" recommendations and a searchable library |
| `/connections` | Incoming requests, your network, pending invitations |
| `/messages` | Conversations and a message thread |

## The part that matters

`WhyThisMatch` (in `src/components/MatchCard.tsx`) renders the API's
`explanation` array: every weighted factor as a labelled bar — teaching
philosophy 30%, subjects 20%, education level 15%, learner level 15%, proximity
10%, class size 10%. Judges can see exactly where a 0.85 came from.

## Layout

```
src/
├── api/
│   ├── client.ts      typed fetch wrapper: base URL, token, error flattening
│   ├── types.ts       the response shapes we render
│   └── vocab.ts       controlled vocabularies + display helpers
├── auth/AuthContext.tsx   session, profile, login/register/logout
├── components/        ui primitives, MatchCard, TeacherCard, ChipSelect
└── pages/             one file per route
```

No state library: the API is fast enough that `useState` + `useCallback` per
page is honest and easier to read.

## Build

```bash
npm run build     # tsc -b && vite build  ->  dist/
npm run preview
```

### Deploying to Render as a static site

```yaml
- type: web
  runtime: static
  name: edumatch-web
  rootDir: frontend
  buildCommand: npm ci && npm run build
  staticPublishPath: ./dist
  envVars:
    - key: VITE_API_URL
      value: https://edumatch-api-asbp.onrender.com
  routes:
    - type: rewrite
      source: /*
      destination: /index.html     # client-side routing
```

Single-page routing needs the rewrite rule above (or Redirects/Rewrites →
`/*` → `/index.html`, status 200); without it a refresh on `/search` 404s.

Set the API's `CORS_ORIGINS` to the deployed frontend origin once it's live.
