import { Link } from "react-router-dom";
import type { TeacherSummary } from "../api/types";
import { humanize } from "../api/vocab";
import { Avatar, Badge, Card, Stars } from "./ui";

export function TeacherCard({ teacher, score }: { teacher: TeacherSummary; score?: number }) {
  const name = `${teacher.first_name} ${teacher.last_name}`;
  return (
    <Card className="h-full p-5" interactive>
      <Link to={`/teachers/${teacher.user_id}`} className="flex h-full items-start gap-4">
        <Avatar name={name} size={46} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate font-semibold text-ink">{name}</p>
            {score !== undefined && (
              <span className="shrink-0 rounded-full bg-indigo-50 px-2 py-1 text-xs font-semibold tabular-nums text-indigo-700">
                {Math.round(score * 100)}% relevant
              </span>
            )}
          </div>
          <p className="truncate text-sm text-muted">
            {[teacher.institution, teacher.location_name].filter(Boolean).join(" · ")}
            {teacher.distance_km !== null && ` · ${Math.round(teacher.distance_km)} km`}
          </p>
          {teacher.teaching_style && (
            <p className="mt-2 line-clamp-2 text-sm leading-5 text-ink/80">{teacher.teaching_style}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {teacher.education_levels.slice(0, 1).map((level) => (
              <Badge key={level} tone="amber">
                {humanize(level)}
              </Badge>
            ))}
            {teacher.subjects.slice(0, 3).map((subject) => (
              <Badge key={subject} tone="emerald">
                {humanize(subject)}
              </Badge>
            ))}
            {teacher.rating_count > 0 && (
              <span className="ml-auto">
                <Stars value={teacher.average_rating} count={teacher.rating_count} />
              </span>
            )}
          </div>
          <p className="mt-3 text-xs font-semibold text-indigo-600">View teaching profile →</p>
        </div>
      </Link>
    </Card>
  );
}
