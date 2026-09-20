import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  const base =
    "press inline-flex items-center justify-center gap-2 rounded-xl font-semibold " +
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 " +
    "disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm",
    secondary: "bg-white text-ink ring-1 ring-line hover:bg-slate-50",
    ghost: "text-muted hover:text-ink hover:bg-slate-100",
    danger: "bg-white text-rose-600 ring-1 ring-rose-200 hover:bg-rose-50",
  };
  const sizes = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2.5 text-sm" };
  return (
    <button
      className={cx(base, variants[variant], sizes[size], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Card({
  className,
  children,
  interactive,
}: {
  className?: string;
  children: ReactNode;
  /** Adds the hover lift. For cards that are themselves a link or a target. */
  interactive?: boolean;
}) {
  return (
    <div
      className={cx(
        "rounded-2xl bg-white ring-1 ring-line shadow-sm",
        interactive && "lift hover:ring-slate-300",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "indigo" | "emerald" | "amber";
}) {
  const tones = {
    neutral: "bg-slate-100 text-slate-700",
    indigo: "bg-indigo-50 text-indigo-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line",
        "transition duration-150 placeholder:text-slate-400 hover:ring-slate-300",
        "focus:outline-none focus:ring-2 focus:ring-indigo-500",
        "disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 disabled:hover:ring-line",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line",
        "transition duration-150 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className ?? "h-5 w-5")} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z"
      />
    </svg>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-64 items-center justify-center gap-3 py-16 text-muted">
      <Spinner />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="p-10 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </Card>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-indigo-600">
            {eyebrow}
          </p>
        )}
        <h1 className="text-3xl font-semibold tracking-[-0.025em] text-ink sm:text-4xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionHeading({
  title,
  description,
  trailing,
}: {
  title: string;
  description?: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {trailing}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">
      {message}
    </div>
  );
}

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  // Stable colour per person: same name, same hue, every render.
  const hue = Array.from(name).reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 360, 7);
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(135deg, hsl(${hue} 62% 52%), hsl(${(hue + 40) % 360} 62% 44%))`,
      }}
    >
      {initials || "?"}
    </div>
  );
}

/** Circular match score. `score` is 0-1; the ring fills proportionally. */
export function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const percent = Math.round(score * 100);
  const colour =
    percent >= 80 ? "oklch(0.62 0.17 155)" : percent >= 60 ? "oklch(0.68 0.16 75)" : "oklch(0.62 0.12 255)";
  return (
    <div
      className="score-ring flex items-center justify-center rounded-full"
      style={
        { width: size, height: size, "--score": score, "--ring-colour": colour } as React.CSSProperties
      }
      aria-label={`${percent} percent match`}
    >
      <div
        className="flex items-center justify-center rounded-full bg-white font-semibold text-ink"
        style={{ width: size - 10, height: size - 10, fontSize: size * 0.26 }}
      >
        {percent}
      </div>
    </div>
  );
}

export function Stars({ value, count }: { value: number; count?: number }) {
  return (
    <span className="inline-flex items-center gap-1 text-sm text-amber-500">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={n <= Math.round(value) ? "" : "text-slate-300"}>
          ★
        </span>
      ))}
      {count !== undefined && (
        <span className="text-xs text-muted">
          {value.toFixed(1)} ({count})
        </span>
      )}
    </span>
  );
}
