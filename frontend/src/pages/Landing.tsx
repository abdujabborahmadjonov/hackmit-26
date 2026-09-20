import { useEffect, useState } from "react";
import { Logo } from "../components/Logo";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ErrorNote } from "../components/ui";

const DEMO = { email: "demo_teacher@example.com", password: "DemoPassword123!" };

/** One exchange from the mentor, shown as the product card. It is the real
 *  shape of a reply - a claim, then where it came from. */
const TRANSCRIPT = [
  { who: "you", text: "My students memorise the syntax and freeze on the first real bug." },
  {
    who: "them",
    text: "Then stop teaching syntax and start teaching the bug. I open every lecture with broken code and two minutes of pair discussion before I run it.",
  },
  { who: "cite", text: "Guest lecture, Winter 2013 · 09:51" },
];

const STEPS = [
  [
    "Write the classroom, not the résumé",
    "Describe how your students actually spend the hour. The matching reads meaning, not keywords.",
  ],
  [
    "Meet the people who fit",
    "Every match arrives with its reasoning: shared subjects, learner level, distance, how close your teaching philosophies sit.",
  ],
  [
    "Talk to an educator who has done it",
    "Ask a mentor in text or out loud. Every claim is cited, and it says so when it has nothing.",
  ],
];

const COMPARISON: [string, string, string, string][] = [
  [
    "How you are matched",
    "Teaching philosophy, read semantically",
    "Subject tags you tick yourself",
    "Whoever posted most recently",
  ],
  [
    "Why this person",
    "Shown, factor by factor, with the score",
    "Not shown",
    "You guess from a bio",
  ],
  [
    "Asking a hard question",
    "A mentor answers, and cites where it came from",
    "Nobody to ask",
    "Ask forty people, hope one replies",
  ],
  [
    "When it does not know",
    "It says so rather than inventing",
    "—",
    "Someone answers confidently anyway",
  ],
];

export default function Landing() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<{ teachers: number; resources: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    // Public endpoints - shows the corpus is real without needing a login.
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
    <div className="min-h-screen bg-white text-slate-900">
      {/* --- nav ----------------------------------------------------------- */}
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-5 sm:px-8">
          <Link to="/" className="press flex shrink-0 items-center gap-2.5 font-semibold tracking-tight">
            <Logo size={32} />
            EduMatch
          </Link>
          <nav className="hidden flex-1 items-center gap-7 text-sm text-slate-600 md:flex">
            <a className="press hover:text-slate-900" href="#how">How it works</a>
            <a className="press hover:text-slate-900" href="#mentor">Mentors</a>
            <a className="press hover:text-slate-900" href="#compare">Compare</a>
          </nav>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <Link
              to="/login"
              className="press rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:text-slate-900"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="press rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* --- hero ---------------------------------------------------------- */}
      <section className="relative overflow-hidden">
        {/* A faint grid, fading out downward, so the white does not read as empty. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_78%)]"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgb(226 232 240 / 0.7) 1px, transparent 1px)," +
              "linear-gradient(to bottom, rgb(226 232 240 / 0.7) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
        />

        <div className="relative mx-auto grid max-w-6xl gap-14 px-5 pb-20 pt-14 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-10 lg:pb-28 lg:pt-20">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 shadow-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-600" />
              New — talk to a mentor, out loud
            </span>

            {/* No hard line breaks: at narrow widths they fight the natural
                wrap and strand a word per line. `text-balance` keeps the lines
                even by itself. */}
            <h1 className="mt-7 max-w-[13ch] text-balance text-[2.5rem] font-semibold leading-[1.02] tracking-[-0.035em] sm:max-w-[14ch] sm:text-[3.25rem] sm:leading-[0.98] lg:text-[4rem]">
              The colleague who teaches like you is out there.
            </h1>

            <p className="mt-6 max-w-lg text-lg leading-7 text-slate-600">
              Describe how you actually teach. EduMatch reads the meaning, not the keywords, and
              shows you exactly why it put you two together.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={tryDemo}
                disabled={busy}
                className="press inline-flex items-center justify-center rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy ? "Opening…" : "Explore the demo"}
              </button>
              <Link
                to="/register"
                className="press inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 hover:bg-slate-50"
              >
                Create an account
              </Link>
            </div>

            <dl className="mt-9 space-y-1.5 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <dt className="font-semibold">No setup</dt>
                <dd className="text-slate-600">the demo account is already furnished</dd>
              </div>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <dt className="font-semibold">Every match explained</dt>
                <dd className="text-slate-600">factor by factor, with the numbers</dd>
              </div>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <dt className="font-semibold">Mentors cite their sources</dt>
                <dd className="text-slate-600">or tell you they have none</dd>
              </div>
            </dl>

            <div className="mt-4">
              <ErrorNote error={error} />
            </div>
          </div>

          {/* The product, as a card - a real exchange rather than a mockup. */}
          <div className="relative">
            <div className="overflow-hidden rounded-2xl bg-slate-900 shadow-2xl ring-1 ring-slate-900/10">
              <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
                <span className="text-xs font-medium text-white/80">Osmar Zaïane</span>
                <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/60">
                  AI persona
                </span>
                <span className="ml-auto flex items-center gap-1.5 text-[11px] text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  live
                </span>
              </div>
              <div className="space-y-3 px-4 py-5">
                {TRANSCRIPT.map((line, index) =>
                  line.who === "cite" ? (
                    <p key={index} className="pl-1 font-mono text-[11px] text-white/35">
                      ↳ {line.text}
                    </p>
                  ) : (
                    <div
                      key={index}
                      className={line.who === "you" ? "flex justify-end" : "flex justify-start"}
                    >
                      <p
                        className={
                          "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-6 " +
                          (line.who === "you"
                            ? "rounded-br-sm bg-indigo-600 text-white"
                            : "rounded-tl-sm bg-white/10 text-white/90")
                        }
                      >
                        {line.text}
                      </p>
                    </div>
                  ),
                )}
              </div>
            </div>
            <p className="mt-3 px-1 text-xs leading-5 text-slate-500">
              An AI persona built with the educator's permission, from material you can check.
            </p>
          </div>
        </div>
      </section>

      {/* --- stats --------------------------------------------------------- */}
      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto grid max-w-6xl divide-slate-200 px-5 sm:px-8 md:grid-cols-3 md:divide-x">
          {[
            [stats ? stats.teachers.toLocaleString() : "—", "educators in the network"],
            [stats ? stats.resources.toLocaleString() : "—", "teaching resources shared"],
            ["6 factors", "behind every match, all visible"],
          ].map(([value, caption]) => (
            <div key={caption} className="px-2 py-8 text-center">
              <p className="text-2xl font-semibold tracking-tight sm:text-3xl">{value}</p>
              <p className="mt-1 text-sm text-slate-600">{caption}</p>
            </div>
          ))}
        </div>
      </section>

      {/* --- how ----------------------------------------------------------- */}
      <section id="how" className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          How it works
        </p>
        <h2 className="mt-4 max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.03em] sm:text-5xl">
          Three steps, and none of them are a keyword search.
        </h2>

        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl bg-slate-200 md:grid-cols-3">
          {STEPS.map(([title, body], index) => (
            <div key={title} className="bg-white p-7">
              <span className="font-mono text-sm text-indigo-600">0{index + 1}</span>
              <h3 className="mt-4 text-lg font-semibold tracking-tight">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* --- mentor -------------------------------------------------------- */}
      <section id="mentor" className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-2 lg:items-center lg:py-28">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Ask a mentor
            </p>
            <h2 className="mt-4 text-3xl font-semibold leading-tight tracking-[-0.03em] sm:text-5xl">
              An educator who answers, and shows their working.
            </h2>
            <p className="mt-6 max-w-lg text-lg leading-7 text-slate-600">
              Type, or press the microphone and talk. Replies arrive as they are written and are
              spoken sentence by sentence, so it moves like a conversation rather than a lookup.
            </p>
            <ul className="mt-8 space-y-3.5">
              {[
                "Every claim carries the source it came from — and the server checks those citations.",
                "A question past their material gets researched, and marked as research rather than recollection.",
                "A persona with nothing on file declines instead of inventing.",
              ].map((point) => (
                <li key={point} className="flex gap-3 text-sm leading-6 text-slate-700">
                  <span aria-hidden className="mt-0.5 text-indigo-600">✓</span>
                  {point}
                </li>
              ))}
            </ul>
            <Link
              to="/register"
              className="press mt-9 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              Meet a mentor
              <span aria-hidden>→</span>
            </Link>
          </div>

          <div className="rounded-2xl bg-white p-2 shadow-xl ring-1 ring-slate-200">
            <div className="rounded-xl bg-slate-900 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-white/90">Osmar Zaïane</p>
                  <p className="text-xs text-white/40">0:42</p>
                </div>
                <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] text-white/60">
                  Speaking
                </span>
              </div>
              <div className="mt-6 grid h-40 place-items-center">
                {/* A stand-in for the avatar - the live one is 10MB of model. */}
                <div className="relative grid h-28 w-28 place-items-center">
                  <span className="absolute inset-0 animate-pulse rounded-full bg-indigo-500/20" />
                  <span className="absolute inset-4 rounded-full bg-indigo-500/30" />
                  <span className="relative h-16 w-16 rounded-full bg-indigo-500/70" />
                </div>
              </div>
              <div className="mt-4 flex items-center justify-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-white/10 text-white/70">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                    <path d="M11 5 6 9H3v6h3l5 4V5Z" />
                    <path d="M15.5 8.5a5 5 0 0 1 0 7" />
                  </svg>
                </span>
                <span className="grid h-14 w-14 place-items-center rounded-full bg-white text-slate-900">
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                    <rect x="9" y="3" width="6" height="11" rx="3" />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                  </svg>
                </span>
                <span className="grid h-10 w-10 place-items-center rounded-full bg-rose-500 text-white">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
                    <path d="M3 10c5-4 13-4 18 0l-2.5 3-4-1.5V9a12 12 0 0 0-5 0v2.5L5.5 13 3 10Z" />
                  </svg>
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --- compare ------------------------------------------------------- */}
      <section id="compare" className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Compare</p>
        <h2 className="mt-4 max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.03em] sm:text-5xl">
          What you get that a directory does not.
        </h2>

        <div className="mt-12 overflow-x-auto">
          <table className="w-full min-w-[46rem] border-separate border-spacing-0 text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-slate-500">
                <th className="rounded-tl-2xl border-y border-l border-slate-200 bg-slate-50 px-5 py-4 font-medium">
                  Feature
                </th>
                <th className="border-y border-slate-200 bg-indigo-50/70 px-5 py-4 font-semibold text-indigo-700">
                  EduMatch
                </th>
                <th className="border-y border-slate-200 bg-slate-50 px-5 py-4 font-medium">
                  A teacher directory
                </th>
                <th className="rounded-tr-2xl border-y border-r border-slate-200 bg-slate-50 px-5 py-4 font-medium">
                  A staffroom group chat
                </th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map(([feature, ours, directory, chat], index) => {
                const last = index === COMPARISON.length - 1;
                return (
                  <tr key={feature} className="align-top">
                    <td className={"border-b border-l border-slate-200 px-5 py-4 font-medium " + (last ? "rounded-bl-2xl" : "")}>
                      {feature}
                    </td>
                    <td className="border-b border-slate-200 bg-indigo-50/40 px-5 py-4">
                      <span className="mr-1.5 text-indigo-600">✓</span>
                      {ours}
                    </td>
                    <td className="border-b border-slate-200 px-5 py-4 text-slate-500">{directory}</td>
                    <td className={"border-b border-r border-slate-200 px-5 py-4 text-slate-500 " + (last ? "rounded-br-2xl" : "")}>
                      {chat}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* --- close --------------------------------------------------------- */}
      <section className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto max-w-6xl px-5 py-20 text-center sm:px-8 lg:py-24">
          <h2 className="mx-auto max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.03em] sm:text-5xl">
            Find the person who already solved it.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg leading-7 text-slate-600">
            The demo account is furnished and waiting. No card, no setup.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={tryDemo}
              disabled={busy}
              className="press inline-flex items-center justify-center rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              {busy ? "Opening…" : "Explore the demo"}
            </button>
            <Link
              to="/register"
              className="press inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-900 hover:bg-slate-50"
            >
              Create an account
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-8 text-sm text-slate-500 sm:px-8">
          <span className="font-semibold text-slate-900">EduMatch</span>
          <span>An AI-powered professional network for educators.</span>
          <Link className="press ml-auto hover:text-slate-900" to="/login">
            Sign in
          </Link>
        </div>
      </footer>
    </div>
  );
}
