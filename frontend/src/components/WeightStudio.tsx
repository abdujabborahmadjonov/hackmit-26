import { FACTOR_META } from "../api/vocab";
import { Donut } from "./Donut";
import { Button, cx } from "./ui";

export type Weights = Record<string, number>;

/** The server's published weights, duplicated here only as a fallback for
 *  views that render a breakdown without having fetched them. */
export const DEFAULT_WEIGHTS: Weights = {
  semantic: 0.3,
  expertise: 0.2,
  education: 0.15,
  teaching_level: 0.15,
  location: 0.1,
  class_size: 0.1,
};

export const FACTOR_ORDER = [
  "semantic",
  "expertise",
  "education",
  "teaching_level",
  "location",
  "class_size",
] as const;

/** Re-score one candidate under arbitrary weights. The weights are normalised
 *  so the total always lands in 0-1 however far the sliders are pushed. */
export function scoreWith(components: Record<string, number>, weights: Weights): number {
  const total = FACTOR_ORDER.reduce((sum, factor) => sum + (weights[factor] ?? 0), 0);
  if (total <= 0) return 0;
  return FACTOR_ORDER.reduce(
    (score, factor) => score + (components[factor] ?? 0) * ((weights[factor] ?? 0) / total),
    0,
  );
}

export function normalise(weights: Weights): Weights {
  const total = FACTOR_ORDER.reduce((sum, f) => sum + (weights[f] ?? 0), 0);
  if (total <= 0) return weights;
  return Object.fromEntries(FACTOR_ORDER.map((f) => [f, (weights[f] ?? 0) / total]));
}

interface WeightStudioProps {
  weights: Weights;
  defaults: Weights;
  onChange: (weights: Weights) => void;
  changed: boolean;
}

export function WeightStudio({ weights, defaults, onChange, changed }: WeightStudioProps) {
  const shown = normalise(weights);

  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-line">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Tune the algorithm</h2>
          <p className="mt-0.5 text-xs text-muted">
            Drag a factor and the ranking re-orders instantly — scored in your browser from the
            same numbers the API returned.
          </p>
        </div>
        {changed && (
          <Button size="sm" variant="ghost" onClick={() => onChange(defaults)}>
            Reset to defaults
          </Button>
        )}
      </div>

      <div className="mt-4 flex flex-col gap-5 sm:flex-row sm:items-center">
        <div className="shrink-0 self-center">
          <Donut
            segments={FACTOR_ORDER.map((factor) => ({
              key: factor,
              label: FACTOR_META[factor].label,
              value: shown[factor] ?? 0,
              colour: FACTOR_META[factor].colour,
            }))}
            size={148}
            thickness={22}
            centreValue="100%"
            centreCaption="of the score"
          />
        </div>
        <div className="grid flex-1 gap-x-6 gap-y-3 sm:grid-cols-2">
        {FACTOR_ORDER.map((factor) => {
          const meta = FACTOR_META[factor];
          const percent = Math.round((shown[factor] ?? 0) * 100);
          const isDefault = Math.abs((shown[factor] ?? 0) - (defaults[factor] ?? 0)) < 0.005;
          return (
            <label key={factor} className="block">
              <div className="flex items-baseline justify-between gap-2">
                <span className="flex items-center gap-1.5 text-sm text-ink">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: meta.colour }}
                  />
                  {meta.label}
                </span>
                <span
                  className={cx(
                    "text-xs tabular-nums",
                    isDefault ? "text-muted" : "font-semibold text-indigo-600",
                  )}
                >
                  {percent}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={60}
                step={1}
                value={Math.round((weights[factor] ?? 0) * 100)}
                onChange={(event) =>
                  onChange({ ...weights, [factor]: Number(event.target.value) / 100 })
                }
                className="mt-1 w-full accent-indigo-600"
                aria-label={`${meta.label} weight`}
              />
            </label>
          );
        })}
        </div>
      </div>
    </div>
  );
}

/** Where a card moved to after re-weighting. */
export function RankDelta({ delta }: { delta: number }) {
  if (delta === 0) return null;
  const up = delta > 0;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-medium",
        up ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600",
      )}
      title={`Moved ${Math.abs(delta)} place${Math.abs(delta) === 1 ? "" : "s"} ${up ? "up" : "down"}`}
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  );
}
