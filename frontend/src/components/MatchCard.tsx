import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Recommendation } from "../api/types";
import { FACTOR_META, humanize } from "../api/vocab";
import { Donut } from "./Donut";
import { DEFAULT_WEIGHTS, FACTOR_ORDER } from "./WeightStudio";
import { Avatar, Badge, Button, Card, ScoreRing, Stars } from "./ui";

/** The "Why this match?" panel.
 *
 *  A match score is a part-to-whole: six weighted factors, plus whatever a
 *  perfect match would have earned and this one didn't. The donut shows that
 *  composition; the table beneath carries the numbers, which is also what makes
 *  the lighter hues legible - three of them fall under 3:1 against white, so
 *  they never have to be read on colour alone.
 */
export function WhyThisMatch({
  recommendation,
  displayScore,
  weights,
}: {
  recommendation: Recommendation;
  displayScore?: number;
  weights?: Record<string, number>;
}) {
  const match_score = displayScore ?? recommendation.match_score;
  const activeWeights = weights ?? DEFAULT_WEIGHTS;
  const labelFor = (factor: string) =>
    recommendation.explanation.find((entry) => entry.factor === factor)?.label;

  // Fixed order - the palette is validated on these adjacencies, wrap included.
  const rows = FACTOR_ORDER.map((factor) => {
    const score = recommendation.components?.[factor] ?? 0;
    const weight = activeWeights[factor] ?? 0;
    return {
      factor,
      meta: FACTOR_META[factor],
      score,
      weight,
      contribution: score * weight,
      label: labelFor(factor),
    };
  });

  return (
    <div className="mt-4 rounded-2xl bg-slate-50 p-4 ring-1 ring-line sm:p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        How this {Math.round(match_score * 100)}% was calculated
      </p>

      <div className="mt-3 flex flex-col items-center gap-5 sm:flex-row sm:items-start">
        <div className="shrink-0">
          <Donut
            segments={rows.map((row) => ({
              key: row.factor,
              label: row.meta.label,
              value: row.contribution,
              colour: row.meta.colour,
            }))}
            total={1}
            centreValue={`${Math.round(match_score * 100)}%`}
            centreCaption="match"
          />
          <p className="mt-1 text-center text-[11px] text-muted">
            Grey is what a perfect match would add
          </p>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted">
              <th className="pb-1 text-left font-medium">Factor</th>
              <th className="pb-1 text-right font-medium">Score</th>
              <th className="pb-1 text-right font-medium">Weight</th>
              <th className="pb-1 text-right font-medium">Adds</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.factor} className="border-t border-line/70">
                <td className="py-1.5">
                  <span className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{ background: row.meta.colour }}
                    />
                    <span className="text-ink">{row.meta.label}</span>
                  </span>
                  {row.label && <span className="block pl-[18px] text-xs text-muted">{row.label}</span>}
                </td>
                <td className="py-1.5 text-right tabular-nums text-ink">
                  {Math.round(row.score * 100)}%
                </td>
                <td className="py-1.5 text-right tabular-nums text-muted">
                  {Math.round(row.weight * 100)}%
                </td>
                <td className="py-1.5 text-right font-medium tabular-nums text-ink">
                  {(row.contribution * 100).toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface MatchCardProps {
  recommendation: Recommendation;
  /** Overrides the API score when the viewer is re-weighting locally. */
  displayScore?: number;
  rankDelta?: ReactNode;
  /** Present when the viewer is re-weighting, so the breakdown matches. */
  weights?: Record<string, number>;
  onConnect?: (userId: string) => void;
  onMessage?: (userId: string) => void;
  onDismiss?: (userId: string) => void;
  connecting?: boolean;
  connected?: boolean;
}

export function MatchCard({
  recommendation,
  displayScore,
  rankDelta,
  weights,
  onConnect,
  onMessage,
  onDismiss,
  connecting,
  connected,
}: MatchCardProps) {
  const [showWhy, setShowWhy] = useState(false);
  const { teacher, reasons } = recommendation;
  const match_score = displayScore ?? recommendation.match_score;
  const name = `${teacher.first_name} ${teacher.last_name}`;

  return (
    <Card className="overflow-hidden" interactive>
      <div className="h-1 bg-gradient-to-r from-indigo-500 via-blue-500 to-emerald-400" />
      <div className="p-5 sm:p-6">
      <div className="flex items-start gap-4">
        <Avatar name={name} size={52} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              to={`/teachers/${teacher.user_id}`}
              className="text-base font-semibold text-ink hover:text-indigo-700"
            >
              {name}
            </Link>
            {teacher.rating_count > 0 && (
              <Stars value={teacher.average_rating} count={teacher.rating_count} />
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {[teacher.institution, teacher.location_name].filter(Boolean).join(" · ")}
            {teacher.distance_km !== null && ` · ${Math.round(teacher.distance_km)} km away`}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {teacher.education_levels.map((level) => (
              <Badge key={level} tone="amber">
                {humanize(level)}
              </Badge>
            ))}
            {teacher.subjects.slice(0, 3).map((subject) => (
              <Badge key={subject} tone="emerald">
                {humanize(subject)}
              </Badge>
            ))}
            {teacher.teaching_methods.slice(0, 2).map((method) => (
              <Badge key={method} tone="indigo">
                {humanize(method)}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex flex-col items-center gap-1.5">
          <ScoreRing score={match_score} />
          {rankDelta}
        </div>
      </div>

      <ul className="mt-5 grid gap-2 rounded-xl bg-slate-50 p-4 ring-1 ring-line/70 sm:grid-cols-2">
        {reasons.map((reason) => (
          <li key={reason} className="flex gap-2 text-sm leading-5 text-slate-700">
            <span aria-hidden className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-emerald-100 text-[10px] text-emerald-700">
              ✓
            </span>
            <span>{reason}</span>
          </li>
        ))}
      </ul>

      {/* Grid-rows trick: animates open without measuring the content height. */}
      <div className="collapsible" data-open={showWhy}>
        <div>
          <WhyThisMatch
            recommendation={recommendation}
            displayScore={match_score}
            weights={weights}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => setShowWhy((open) => !open)}>
          {showWhy ? "Hide breakdown" : "Why this match?"}
        </Button>
        {onConnect && (
          <Button
            size="sm"
            onClick={() => onConnect(teacher.user_id)}
            loading={connecting}
            disabled={connected}
          >
            {connected ? "Request sent" : "Connect"}
          </Button>
        )}
        {onMessage && (
          <Button size="sm" variant="ghost" onClick={() => onMessage(teacher.user_id)}>
            Message
          </Button>
        )}
        {onDismiss && (
          <Button size="sm" variant="ghost" onClick={() => onDismiss(teacher.user_id)}>
            Not a fit
          </Button>
        )}
        <Link
          to={`/teachers/${teacher.user_id}`}
          className="ml-auto text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          View profile →
        </Link>
      </div>
      </div>
    </Card>
  );
}
