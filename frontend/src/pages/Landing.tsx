import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { FACTOR_META } from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import { Donut } from "../components/Donut";
import { FACTOR_ORDER } from "../components/WeightStudio";
import { ErrorNote } from "../components/ui";

const DEMO = { email: "demo_teacher@example.com", password: "DemoPassword123!" };

const WEIGHTS: Record<string, number> = {
  semantic: 0.3,
  expertise: 0.2,
  education: 0.15,
  teaching_level: 0.15,
  location: 0.1,
  class_size: 0.1,
};

const PEOPLE = [
  {
    initials: "BM",
    name: "Bob",
    detail: "Project-based CS",
    score: 94,
    className: "left-[8%] top-[16%] sm:left-[12%]",
    tone: "bg-[#d9ff63] text-[#10201c]",
  },
  {
    initials: "CW",
    name: "Carol",
    detail: "Socratic ML",
    score: 78,
    className: "right-[3%] top-[12%] sm:right-[8%]",
    tone: "bg-[#ffb7d5] text-[#341424]",
  },
  {
    initials: "DR",
    name: "Dana",
    detail: "Hands-on physics",
    score: 87,
    className: "right-[1%] bottom-[13%] sm:right-[5%]",
    tone: "bg-[#a5d8ff] text-[#10243a]",
  },
  {
    initials: "TG",
    name: "Tim",
    detail: "Collaborative robotics",
    score: 82,
    className: "bottom-[8%] left-[7%] sm:left-[13%]",
    tone: "bg-[#ffd28a] text-[#35200b]",
  },
];

const STEPS = [
  ["01", "Write the classroom, not the résumé", "Describe the energy, routines, and beliefs that shape how your students learn."],
  ["02", "Find meaning between the words", "Semantic matching recognizes that “students ship” and “learners build” belong together."],
  ["03", "Meet with context, not a cold intro", "Every recommendation arrives with shared ground and a transparent reason to connect."],
];

const linkButton =
  "press inline-flex items-center justify-center rounded-full px-4 py-2 text-sm font-semibold " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#d9ff63] focus-visible:ring-offset-2";

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
    <div className="min-h-screen overflow-hidden bg-[#f4f5ec] text-[#10201c]">
      <section className="relative min-h-[900px] overflow-hidden bg-[#07110f] text-white lg:min-h-screen">
        <div className="landing-grid absolute inset-0 opacity-40" aria-hidden="true" />
        <div className="landing-glow absolute inset-0" aria-hidden="true" />

        <header className="relative z-20 mx-auto flex max-w-[1440px] items-center justify-between px-5 py-5 sm:px-8 lg:px-12">
          <Link to="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#d9ff63] text-sm text-[#07110f]">
              E
            </span>
            EduMatch
          </Link>
          <nav className="hidden items-center gap-7 text-sm text-white/60 md:flex">
            <a href="#method" className="transition hover:text-white">How it works</a>
            <a href="#why" className="transition hover:text-white">Why it matches</a>
            <a href="#network" className="transition hover:text-white">The network</a>
          </nav>
          <div className="flex items-center gap-1.5">
            <Link to="/login" className={`${linkButton} text-white/70 hover:text-white`}>
              Sign in
            </Link>
            <Link
              to="/register"
              className={`${linkButton} bg-white text-[#07110f] hover:bg-[#d9ff63]`}
            >
              Join the network
            </Link>
          </div>
        </header>

        <div className="relative z-10 mx-auto grid max-w-[1440px] gap-10 px-5 pb-10 pt-16 sm:px-8 lg:min-h-[calc(100vh-80px)] lg:grid-cols-[0.88fr_1.12fr] lg:items-center lg:px-12 lg:pb-12 lg:pt-6">
          <div className="relative z-10 max-w-2xl">
            <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#d9ff63]">
              <span className="h-px w-8 bg-[#d9ff63]" />
              A living network for educators
            </p>
            <h1 className="mt-7 text-5xl font-medium leading-[0.94] tracking-[-0.055em] sm:text-7xl lg:text-[6.5rem]">
              Your teaching has a signal.
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-white/65 sm:text-xl">
              EduMatch finds the people who recognize it—through the philosophy, methods, and
              classroom instincts that never fit neatly on a résumé.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={tryDemo}
                disabled={busy}
                className="press inline-flex items-center gap-2 rounded-full bg-[#d9ff63] px-6 py-3 text-base font-semibold text-[#07110f] hover:bg-[#e5ff93] disabled:cursor-wait disabled:opacity-60"
              >
                {busy ? "Opening Alice's network…" : "Enter Alice's network"}
                {!busy && <span aria-hidden>↗</span>}
              </button>
              <Link
                to="/register"
                className={`${linkButton} px-6 py-3 text-base text-white ring-1 ring-white/20 hover:bg-white/10`}
              >
                Create your signal
              </Link>
            </div>
            <div className="mt-4 max-w-lg">
              <ErrorNote error={error} />
            </div>
            <p className="mt-4 text-xs text-white/40">
              No setup for the demo. Meet Alice, then see why Bob is her strongest match.
            </p>
          </div>

          <div className="relative mx-auto h-[500px] w-full max-w-[660px] sm:h-[620px]">
            <svg
              aria-hidden="true"
              className="absolute inset-0 h-full w-full overflow-visible"
              viewBox="0 0 660 620"
              fill="none"
            >
              <circle className="landing-orbit-spin origin-center" cx="330" cy="310" r="235" stroke="white" strokeOpacity=".12" strokeDasharray="3 12" />
              <circle className="landing-orbit-spin-reverse origin-center" cx="330" cy="310" r="173" stroke="#d9ff63" strokeOpacity=".25" strokeDasharray="2 8" />
              <circle cx="330" cy="310" r="112" stroke="white" strokeOpacity=".1" />
              <path d="M151 150 330 310 550 130M330 310 585 475M330 310 120 500" stroke="white" strokeOpacity=".12" strokeDasharray="4 8" />
              <path d="M82 328c72-175 235-267 403-210 87 30 137 93 154 174" stroke="#d9ff63" strokeOpacity=".16" />
              <circle cx="330" cy="310" r="5" fill="#d9ff63" />
            </svg>

            <div className="landing-pulse absolute left-1/2 top-1/2 flex h-48 w-48 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border border-[#d9ff63]/40 bg-[#0d1d19]/90 text-center shadow-[0_0_80px_rgba(217,255,99,0.12)] backdrop-blur sm:h-56 sm:w-56">
              <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[#d9ff63]">
                Your teaching signal
              </span>
              <strong className="mt-2 text-2xl font-medium sm:text-3xl">Alice</strong>
              <span className="mt-1 text-xs text-white/45">Project-based CS · Boston</span>
              <div className="mt-4 flex gap-1.5">
                <span className="rounded-full bg-white/10 px-2 py-1 text-[10px] text-white/70">build</span>
                <span className="rounded-full bg-white/10 px-2 py-1 text-[10px] text-white/70">review</span>
                <span className="rounded-full bg-white/10 px-2 py-1 text-[10px] text-white/70">ship</span>
              </div>
            </div>

            {PEOPLE.map((person, index) => (
              <div
                key={person.name}
                className={`landing-float absolute ${person.className}`}
                style={{ animationDelay: `${index * -1.1}s` }}
              >
                <div className="flex items-center gap-2.5 rounded-full border border-white/15 bg-[#0b1715]/85 py-2 pl-2 pr-3 shadow-2xl backdrop-blur-md">
                  <span className={`grid h-9 w-9 place-items-center rounded-full text-xs font-bold ${person.tone}`}>
                    {person.initials}
                  </span>
                  <span>
                    <span className="block text-xs font-semibold">{person.name}</span>
                    <span className="block max-w-28 truncate text-[10px] text-white/45">{person.detail}</span>
                  </span>
                  <strong className="ml-1 text-sm font-medium text-[#d9ff63]">{person.score}</strong>
                </div>
              </div>
            ))}

            <div className="absolute left-1/2 top-[8%] -translate-x-1/2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.16em] text-white/45 backdrop-blur">
              compatibility field · live
            </div>
          </div>
        </div>

        <div className="relative z-10 mx-auto grid max-w-[1440px] grid-cols-3 border-t border-white/10 px-5 sm:px-8 lg:px-12">
          {[
            ["Educators", stats ? stats.teachers.toLocaleString() : "10k+"],
            ["Shared resources", stats ? stats.resources.toLocaleString() : "50k+"],
            ["Visible match signals", "6"],
          ].map(([label, value]) => (
            <div key={label} className="border-r border-white/10 py-5 pr-3 last:border-0 sm:py-6 sm:pr-6">
              <p className="text-[10px] uppercase tracking-[0.16em] text-white/35">{label}</p>
              <p className="mt-1 text-xl font-medium text-white sm:text-2xl">{value}</p>
            </div>
          ))}
        </div>
      </section>

      <main>
        <section id="method" className="mx-auto max-w-[1440px] px-5 py-24 sm:px-8 lg:px-12 lg:py-36">
          <div className="grid gap-12 lg:grid-cols-[0.72fr_1.28fr]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-800">
                How a network should begin
              </p>
              <h2 className="mt-5 text-4xl font-medium leading-tight tracking-[-0.04em] sm:text-5xl">
                Not with a title. With a point of view.
              </h2>
            </div>
            <p className="max-w-2xl text-xl leading-8 text-[#53605a] lg:pt-9 lg:text-2xl lg:leading-10">
              Educators rarely need more contacts. They need the right context to recognize a
              collaborator worth knowing.
            </p>
          </div>

          <div className="mt-20 border-t border-[#cbd1c4]">
            {STEPS.map(([number, title, body]) => (
              <article key={number} className="grid gap-4 border-b border-[#cbd1c4] py-8 sm:grid-cols-[100px_1fr_1fr] sm:items-start sm:py-10">
                <span className="font-mono text-sm text-emerald-800">{number}</span>
                <h3 className="text-xl font-medium tracking-tight sm:text-2xl">{title}</h3>
                <p className="max-w-lg text-sm leading-6 text-[#66716b] sm:text-base sm:leading-7">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="why" className="bg-[#10201c] px-5 py-24 text-white sm:px-8 lg:py-32">
          <div className="mx-auto grid max-w-[1340px] items-center gap-16 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#d9ff63]">
                Nothing hidden in the score
              </p>
              <h2 className="mt-5 max-w-xl text-4xl font-medium leading-tight tracking-[-0.04em] sm:text-6xl">
                Chemistry you can actually inspect.
              </h2>
              <p className="mt-6 max-w-xl text-lg leading-8 text-white/55">
                A 94% match is not a magic number. It is teaching philosophy, subject overlap,
                learner level, proximity, and classroom context—each visible and adjustable.
              </p>
              <button
                type="button"
                onClick={tryDemo}
                className="press mt-8 inline-flex items-center gap-2 rounded-full border border-white/20 px-5 py-3 text-sm font-semibold hover:bg-white/10"
              >
                Open a real breakdown <span aria-hidden>→</span>
              </button>
            </div>

            <div className="landing-dark-donut rounded-[2rem] border border-white/10 bg-white/[0.04] p-6 sm:p-10">
              <div className="flex flex-col items-center gap-8 sm:flex-row">
                <Donut
                  segments={FACTOR_ORDER.map((factor) => ({
                    key: factor,
                    label: FACTOR_META[factor].label,
                    value: WEIGHTS[factor],
                    colour: FACTOR_META[factor].colour,
                  }))}
                  size={220}
                  thickness={32}
                  centreValue="100%"
                  centreCaption="explained"
                />
                <ul className="w-full flex-1">
                  {FACTOR_ORDER.map((factor) => (
                    <li key={factor} className="flex items-center gap-3 border-b border-white/10 py-3 text-sm">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: FACTOR_META[factor].colour }} />
                      <span className="text-white/75">{FACTOR_META[factor].label}</span>
                      <span className="ml-auto font-mono text-white/40">{Math.round(WEIGHTS[factor] * 100)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="network" className="bg-[#d9ff63] px-5 py-24 sm:px-8 lg:py-32">
          <div className="mx-auto max-w-[1340px]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-950/60">
              The next useful person in your career
            </p>
            <div className="mt-5 flex flex-col items-start justify-between gap-10 lg:flex-row lg:items-end">
              <h2 className="max-w-4xl text-5xl font-medium leading-[0.98] tracking-[-0.05em] sm:text-7xl">
                They may already teach four kilometres away.
              </h2>
              <button
                type="button"
                onClick={tryDemo}
                disabled={busy}
                className="press inline-flex shrink-0 items-center gap-2 rounded-full bg-[#07110f] px-6 py-3 text-base font-semibold text-white hover:bg-[#17312a] disabled:cursor-wait disabled:opacity-60"
              >
                {busy ? "Opening the network…" : "Find the signal"} <span aria-hidden>↗</span>
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-[#07110f] px-5 py-8 text-white/40 sm:px-8">
        <div className="mx-auto flex max-w-[1340px] flex-col justify-between gap-4 text-xs sm:flex-row">
          <span>EduMatch · Built for HackMIT 2026</span>
          <span>FastAPI · pgvector · React</span>
        </div>
      </footer>
    </div>
  );
}
