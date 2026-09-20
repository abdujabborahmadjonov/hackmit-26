import type { ReactNode } from "react";
import { Logo } from "./Logo";
import { Link } from "react-router-dom";
import { Avatar, Badge, ScoreRing } from "./ui";

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[1fr_0.9fr]">
      <div className="flex min-h-screen flex-col px-5 py-5 sm:px-10 lg:px-16">
        <Link to="/" className="flex w-fit items-center gap-2.5 font-semibold tracking-tight text-ink">
          <Logo size={32} />
          EduMatch
        </Link>

        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-12">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-indigo-600">
            {eyebrow}
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.025em] text-ink sm:text-4xl">
            {title}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">{description}</p>
          <div className="mt-8">{children}</div>
          <div className="mt-6 text-center text-sm text-muted">{footer}</div>
        </div>

        <p className="text-xs text-muted">Built for educators · Explainable by design</p>
      </div>

      <aside className="relative hidden overflow-hidden bg-indigo-600 p-10 text-white lg:flex lg:flex-col lg:justify-center">
        <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-white/10 blur-3xl" />
        <div className="absolute -bottom-32 -left-24 h-96 w-96 rounded-full bg-cyan-300/10 blur-3xl" />
        <div className="relative mx-auto w-full max-w-md">
          <p className="text-sm font-medium text-indigo-200">A better professional introduction</p>
          <h2 className="mt-3 text-4xl font-semibold leading-tight tracking-tight">
            Start with how you teach, not just where you work.
          </h2>
          <p className="mt-4 max-w-sm text-sm leading-6 text-indigo-100">
            Semantic matching finds the colleagues whose classroom instincts, methods, and goals
            complement your own.
          </p>

          <div className="mt-10 rounded-2xl bg-white p-5 text-ink shadow-2xl shadow-indigo-950/20">
            <div className="flex items-start gap-3">
              <Avatar name="Bob Martinez" size={48} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-semibold">Bob Martinez</p>
                  <Badge tone="emerald">Top match</Badge>
                </div>
                <p className="mt-0.5 text-xs text-muted">Project-based CS · Cambridge, MA</p>
              </div>
              <ScoreRing score={0.94} size={52} />
            </div>
            <blockquote className="mt-4 rounded-xl bg-indigo-50 p-4 text-sm leading-6 text-slate-700">
              “Students work in pairs to ship a working app each unit, with peer review built into
              the process.”
            </blockquote>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-slate-50 p-2">
                <strong className="block text-sm text-ink">96%</strong>
                <span className="text-muted">philosophy</span>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <strong className="block text-sm text-ink">92%</strong>
                <span className="text-muted">subjects</span>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <strong className="block text-sm text-ink">4 km</strong>
                <span className="text-muted">away</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
