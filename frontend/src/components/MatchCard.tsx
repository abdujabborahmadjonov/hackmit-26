import { useState } from "react";
import { Link } from "react-router-dom";
import type { Recommendation } from "../api/types";
import { FACTOR_META, humanize } from "../api/vocab";
import { Avatar, Badge, Button, Card, ScoreRing, Stars } from "./ui";

/** The "Why this match?" panel: every weighted factor, as a bar. */
export function WhyThisMatch({ recommendation }: { recommendation: Recommendation }) {
  const { explanation, match_score } = recommendation;
  return (
    <div className="rise mt-4 rounded-lg bg-slate-50 p-4 ring-1 ring-line">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        How this {Math.round(match_score * 100)}% was calculated
      </p>
      <ul className="mt-3 space-y-3">
        {explanation.map((factor) => {
          const meta = FACTOR_META[factor.factor] ?? {
            label: humanize(factor.factor),
            colour: "bg-slate-400",
          };
          return (
            <li key={factor.factor}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium text-ink">{meta.label}</span>
                <span className="tabular-nums text-xs text-muted">
                  {Math.round(factor.score * 100)}% × {Math.round(factor.weight * 100)}% weight
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
                <div
                  className={`h-full rounded-full ${meta.colour}`}
                  style={{ width: `${Math.max(factor.score * 100, 2)}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-muted">{factor.label}</p>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
        Scores are weighted and summed — teaching philosophy counts most (30%), then subject
        overlap (20%), education and learner level (15% each), proximity and class size (10% each).
      </p>
    </div>
  );
}

interface MatchCardProps {
  recommendation: Recommendation;
  onConnect?: (userId: string) => void;
  onMessage?: (userId: string) => void;
  connecting?: boolean;
  connected?: boolean;
}

export function MatchCard({
  recommendation,
  onConnect,
  onMessage,
  connecting,
  connected,
}: MatchCardProps) {
  const [showWhy, setShowWhy] = useState(false);
  const { teacher, match_score, reasons } = recommendation;
  const name = `${teacher.first_name} ${teacher.last_name}`;

  return (
    <Card className="p-5">
      <div className="flex items-start gap-4">
        <Avatar name={name} size={48} />
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
        <ScoreRing score={match_score} />
      </div>

      <ul className="mt-4 space-y-1.5">
        {reasons.map((reason) => (
          <li key={reason} className="flex gap-2 text-sm text-ink">
            <span aria-hidden className="mt-0.5 text-emerald-600">
              ✓
            </span>
            <span>{reason}</span>
          </li>
        ))}
      </ul>

      {showWhy && <WhyThisMatch recommendation={recommendation} />}

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
        <Link
          to={`/teachers/${teacher.user_id}`}
          className="ml-auto text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          View profile →
        </Link>
      </div>
    </Card>
  );
}
