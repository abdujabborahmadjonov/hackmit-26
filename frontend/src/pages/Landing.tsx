import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { FACTOR_META } from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import { Donut } from "../components/Donut";
import { FACTOR_ORDER } from "../components/WeightStudio";
import { Avatar, Badge, Button, ErrorNote, ScoreRing } from "../components/ui";

const DEMO = { email: "demo_teacher@example.com", password: "DemoPassword123!" };

const WEIGHTS: Record<string, number> = {
  semantic: 0.3,
  expertise: 0.2,
  education: 0.15,
  teaching_level: 0.15,
  location: 0.1,
  class_size: 0.1,
};

const STEPS = [
  {
    eyebrow: "Your context",
    title: "Describe how you teach",
    body: "Not just your subject — your classroom. “Project-based, students ship a working app each unit.”",
  },
  {
    eyebrow: "Semantic matching",
    title: "We read it, not just index it",
    body: "Your teaching style becomes a vector stored in pgvector, so “hands-on builds” finds “students construct” too.",
  },
  {
    eyebrow: "Clear results",
    title: "See who fits, and why",
    body: "Every match shows its reasons — shared subjects, same level, distance, class size — and the maths behind them.",
  },
];

const PREVIEW_FACTORS = [
  { label: "Teaching philosophy", score: 0.96, colour: FACTOR_META.semantic.colour },
  { label: "Subjects & expertise", score: 0.92, colour: FACTOR_META.expertise.colour },
  { label: "Education level", score: 1, colour: FACTOR_META.education.colour },
];

const linkButton =
  "press inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-sm font-medium " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2";

export default function Landing() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<{ teachers: number; resources: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    // Public endpoints - shows the demo corpus is real without needing a login.
    void Promise.all([api.searchTeachers({ limit: 1 }), api.resources({ limit: 1 })])
      .then(([teachers, resources]) =>
        setStats({ teachers: teachers.total, resources: resources.total }),
      )
      .catch(() => setStats(null));
  }, []);

  async function tryDemo() {
    setBusy(true);
    setError(null);
    try {
      await login(DEMO.email, DEMO.password);
      navigate("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen overflow-hidden bg-paper">
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-6">
        <span className="flex items-center gap-2.5 font-semibold tracking-tight text-ink">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-600 text-sm text-white shadow-sm">
            E
          </span>
          EduMatch
        </span>
        <div className="flex items-center gap-2">
          <Link
            to="/login"
            className={`${linkButton} text-muted hover:bg-slate-100 hover:text-ink`}
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className={`${linkButton} bg-indigo-600 text-white shadow-sm hover:bg-indigo-700`}
          >
            Create account
          </Link>
        </div>
      </header>

      <main>
        <section className="relative">
          <div
            className="pointer-events-none absolute -right-32 -top-32 h-[34rem] w-[34rem] rounded-full bg-indigo-100/60 blur-3xl"
            aria-hidden="true"
          />
          <div
            className="pointer-events-none absolute -left-48 top-80 h-80 w-80 rounded-full bg-emerald-100/45 blur-3xl"
            aria-hidden="true"
          />

          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-12 sm:px-6 sm:pt-20 lg:grid-cols-[1.02fr_0.98fr] lg:gap-16 lg:pb-28 lg:pt-24">
            <div className="rise">
              <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 ring-1 ring-indigo-100">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
                Explainable matching for educators
              </div>
              <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-[1.08] tracking-[-0.035em] text-ink sm:text-6xl">
                Meet the educator who gets how you teach.
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-muted">
                EduMatch looks beyond job titles and subject lists. It understands your teaching
                philosophy, finds compatible collaborators, and explains every introduction.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Button
                  onClick={tryDemo}
                  loading={busy}
                  className="px-5 py-3 text-base shadow-lg shadow-indigo-600/20 hover:shadow-indigo-600/30"
                >
                  Explore Alice's matches
                  {!busy && (
                    <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="none">
                      <path
                        d="M4 10h12m-5-5 5 5-5 5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </Button>
                <Link
                  to="/register"
                  className={`${linkButton} bg-white px-5 py-3 text-base text-ink ring-1 ring-line hover:bg-slate-50`}
                >
                  Build your profile
                </Link>
              </div>
              <div className="mt-3 max-w-md">
                <ErrorNote error={error} />
              </div>
              <p className="mt-4 text-xs leading-5 text-muted">
                No setup needed. The demo signs you in as Alice, a project-based CS teacher in
                Boston.
              </p>

              <dl className="mt-10 grid max-w-lg grid-cols-3 divide-x divide-line border-y border-line py-4">
                <div className="pr-4">
                  <dt className="text-xs text-muted">Educators</dt>
                  <dd className="mt-1 text-lg font-semibold text-ink">
                    {stats ? stats.teachers.toLocaleString() : "10k+"}
                  </dd>
                </div>
                <div className="px-4">
                  <dt className="text-xs text-muted">Resources</dt>
                  <dd className="mt-1 text-lg font-semibold text-ink">
                    {stats ? stats.resources.toLocaleString() : "50k+"}
                  </dd>
                </div>
                <div className="pl-4">
                  <dt className="text-xs text-muted">Match factors</dt>
                  <dd className="mt-1 text-lg font-semibold text-ink">6</dd>
                </div>
              </dl>
            </div>

            <div className="rise relative mx-auto w-full max-w-xl lg:mx-0">
              <div
                className="absolute -inset-6 -z-10 rounded-[2rem] bg-indigo-100/55 blur-2xl"
                aria-hidden="true"
              />
              <div className="overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200 shadow-2xl shadow-indigo-950/10">
                <div className="flex items-center justify-between border-b border-line bg-slate-50/80 px-5 py-3.5">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-rose-300" />
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
                  </div>
                  <span className="text-[11px] font-medium text-muted">YOUR TOP MATCH</span>
                  <span className="w-12" />
                </div>

                <div className="p-5 sm:p-7">
                  <div className="flex items-start gap-4">
                    <Avatar name="Bob Martinez" size={56} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold text-ink">Bob Martinez</h2>
                        <Badge tone="emerald">Great fit</Badge>
                      </div>
                      <p className="mt-0.5 text-sm text-muted">
                        Computer Science · Cambridge Rindge & Latin
                      </p>
                      <p className="mt-1 text-xs text-muted">Cambridge, MA · 4 km away</p>
                    </div>
                    <ScoreRing score={0.94} size={62} />
                  </div>

                  <div className="mt-5 rounded-xl bg-indigo-50/70 p-4 ring-1 ring-indigo-100">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-700">
                      Why Bob stands out
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-700">
                      You both turn CS classes into collaborative studios where students ship real
                      projects, review each other's work, and improve in public.
                    </p>
                  </div>

                  <div className="mt-5 space-y-3.5">
                    {PREVIEW_FACTORS.map((factor) => (
                      <div key={factor.label}>
                        <div className="mb-1.5 flex items-center justify-between text-xs">
                          <span className="font-medium text-slate-700">{factor.label}</span>
                          <span className="tabular-nums text-muted">
                            {Math.round(factor.score * 100)}%
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${factor.score * 100}%`,
                              backgroundColor: factor.colour,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-5">
                    <Badge tone="indigo">Project based</Badge>
                    <Badge>Python</Badge>
                    <Badge>High school</Badge>
                    <Badge>Collaborative</Badge>
                  </div>
                </div>
              </div>

              <div className="absolute -bottom-7 -left-4 hidden items-center gap-3 rounded-xl bg-white px-4 py-3 ring-1 ring-line shadow-lg sm:flex">
                <span className="grid h-8 w-8 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                  <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="none">
                    <path
                      d="m5 10 3 3 7-7"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <div>
                  <p className="text-xs font-semibold text-ink">No black-box score</p>
                  <p className="text-[11px] text-muted">Every factor is visible</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="border-y border-line bg-white">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
                From profile to partnership
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
                Matching that starts with your classroom.
              </h2>
              <p className="mt-4 text-base leading-7 text-muted">
                A short profile becomes a ranked, transparent set of educators you can actually
                learn from and build with.
              </p>
            </div>

            <div className="stagger mt-10 grid gap-4 md:grid-cols-3">
              {STEPS.map((step, index) => (
                <article
                  key={step.title}
                  className="relative overflow-hidden rounded-2xl bg-paper p-6 ring-1 ring-line"
                >
                  <div className="flex items-center justify-between">
                    <span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-sm font-semibold text-white shadow-sm">
                      {index + 1}
                    </span>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                      {step.eyebrow}
                    </span>
                  </div>
                  <h3 className="mt-8 text-lg font-semibold text-ink">{step.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-muted">{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:py-24">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
              Transparent by design
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
              Six signals. One match you can trust.
            </h2>
            <p className="mt-4 max-w-lg text-base leading-7 text-muted">
              Every score is a weighted sum of six comparable factors. Open any result to see the
              exact contribution—or tune the weights and watch your ranking update live.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-line">
                Explainable
              </span>
              <span className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-line">
                Adjustable
              </span>
              <span className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-line">
                Built for educators
              </span>
            </div>
          </div>

          <div className="flex flex-col items-center gap-8 rounded-2xl bg-white p-6 ring-1 ring-line shadow-sm sm:flex-row sm:p-8">
            <Donut
              segments={FACTOR_ORDER.map((factor) => ({
                key: factor,
                label: FACTOR_META[factor].label,
                value: WEIGHTS[factor],
                colour: FACTOR_META[factor].colour,
              }))}
              size={200}
              thickness={30}
              centreValue="100%"
              centreCaption="of a match score"
            />
            <ul className="w-full flex-1 space-y-2">
              {FACTOR_ORDER.map((factor) => (
                <li
                  key={factor}
                  className="flex items-center gap-3 border-b border-line/70 pb-2 text-sm last:border-0"
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-sm"
                    style={{ background: FACTOR_META[factor].colour }}
                  />
                  <span className="text-ink">{FACTOR_META[factor].label}</span>
                  <span className="ml-auto tabular-nums text-muted">
                    {Math.round(WEIGHTS[factor] * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="px-5 pb-20 sm:px-6">
          <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-7 overflow-hidden rounded-3xl bg-indigo-600 px-7 py-10 text-white sm:px-10 sm:py-12 lg:flex-row lg:items-center">
            <div>
              <p className="text-sm font-medium text-indigo-200">Your best collaborator may be nearby.</p>
              <h2 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight">
                See who understands your classroom.
              </h2>
            </div>
            <Button
              onClick={tryDemo}
              loading={busy}
              className="shrink-0 bg-white px-5 py-3 text-base text-indigo-700 shadow-none hover:bg-indigo-50"
            >
              Try the live demo
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-line py-8 text-center text-xs text-muted">
        Built for HackMIT 2026 · FastAPI · PostgreSQL + pgvector · React
      </footer>
    </div>
  );
}
