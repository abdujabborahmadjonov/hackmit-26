import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { FACTOR_META } from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import { FACTOR_ORDER } from "../components/WeightStudio";
import { Button, ErrorNote } from "../components/ui";

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
    title: "Describe how you teach",
    body: "Not just your subject — your classroom. “Project-based, students ship a working app each unit.”",
  },
  {
    title: "We read it, not just index it",
    body: "Your teaching style becomes a vector stored in pgvector, so “hands-on builds” finds “students construct” too.",
  },
  {
    title: "See who fits, and why",
    body: "Every match shows its reasons — shared subjects, same level, distance, class size — and the maths behind them.",
  },
];

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
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-5">
        <span className="flex items-center gap-2 font-semibold text-ink">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-indigo-600 text-sm text-white">
            E
          </span>
          EduMatch
        </span>
        <div className="flex items-center gap-2">
          <Link to="/login">
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
          </Link>
          <Link to="/register">
            <Button size="sm">Create account</Button>
          </Link>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-4 pb-12 pt-10 sm:pt-16">
        <p className="text-sm font-medium text-indigo-600">A professional network for educators</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
          Find the teachers you'll actually work well with.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          Every network matches on what you teach. EduMatch matches on <em>how</em> — reading your
          teaching philosophy semantically, then weighing it against subject, level, distance and
          class size. And it shows its work.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Button onClick={tryDemo} loading={busy} className="px-5 py-2.5 text-base">
            Try the live demo
          </Button>
          <Link to="/register">
            <Button variant="secondary" className="px-5 py-2.5 text-base">
              Create an account
            </Button>
          </Link>
          {stats && (
            <p className="text-sm text-muted">
              {stats.teachers.toLocaleString()} educators ·{" "}
              {stats.resources.toLocaleString()} resources indexed
            </p>
          )}
        </div>
        <div className="mt-3 max-w-md">
          <ErrorNote error={error} />
        </div>
        <p className="mt-3 text-xs text-muted">
          The demo signs you in as Alice — a high-school CS teacher in Boston who runs everything as
          a project. Her top match is 4 km away.
        </p>
      </section>

      <section className="border-y border-line bg-white">
        <div className="mx-auto grid max-w-5xl gap-8 px-4 py-12 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <div key={step.title}>
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-indigo-50 text-sm font-semibold text-indigo-700">
                {index + 1}
              </span>
              <h2 className="mt-3 font-semibold text-ink">{step.title}</h2>
              <p className="mt-1 text-sm text-muted">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-14">
        <h2 className="text-xl font-semibold tracking-tight text-ink">
          Every score is six numbers, not a black box
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          A match is a weighted sum of six comparable factors. You can see each one on every match —
          and inside the app, drag the weights and watch the ranking re-order live.
        </p>

        <div className="mt-6 space-y-3">
          {FACTOR_ORDER.map((factor) => {
            const meta = FACTOR_META[factor];
            const weight = WEIGHTS[factor];
            return (
              <div key={factor} className="flex items-center gap-4">
                <span className="w-44 shrink-0 text-sm text-ink">{meta.label}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={`h-full rounded-full ${meta.colour}`}
                    style={{ width: `${weight * 100 * 2.6}%` }}
                  />
                </div>
                <span className="w-10 shrink-0 text-right text-sm tabular-nums text-muted">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <footer className="border-t border-line py-8 text-center text-xs text-muted">
        Built for HackMIT 2026 · FastAPI · PostgreSQL + pgvector · React
      </footer>
    </div>
  );
}
