import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Mentor } from "../api/types";
import { humanize } from "../api/vocab";
import { Avatar, Badge, Card, ErrorNote, Loading, PageHeader } from "../components/ui";

/** Who you can talk to. Each one opens its own profile. */
export default function Mentors() {
  const [mentors, setMentors] = useState<Mentor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.mentors().then(setMentors).catch(setError).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loading label="Finding your mentors" />;

  return (
    <div>
      <PageHeader
        eyebrow="EduMatch AI"
        title="Learn from an educator"
        description="Each one answers from material you can check — and says so when it has none."
      />
      <ErrorNote error={error} />

      <div className="stagger mt-7 grid gap-4 sm:grid-cols-2">
        {mentors.map((mentor) => {
          const guide = mentor.mode === "guide";
          return (
            <Card key={mentor.slug} className="h-full p-6" interactive>
              <Link to={`/mentor/${mentor.slug}`} className="flex h-full flex-col">
                <div className="flex items-start gap-4">
                  <Avatar
                    name={mentor.avatar_seed || mentor.name}
                    src={mentor.avatar_url}
                    size={52}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold text-ink">{mentor.name}</p>
                      <Badge tone="indigo">{guide ? "AI guide" : "AI persona"}</Badge>
                      {mentor.pinned && <Badge tone="amber">Pinned</Badge>}
                    </div>
                    <p className="truncate text-sm text-muted">
                      {[mentor.title, mentor.institution].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                </div>

                {mentor.tagline && (
                  <p className="mt-4 line-clamp-2 text-sm leading-6 text-ink/80">
                    {mentor.tagline}
                  </p>
                )}

                <div className="mt-4 flex flex-wrap gap-1.5">
                  {mentor.subjects.slice(0, 3).map((subject) => (
                    <Badge key={subject} tone="neutral">
                      {humanize(subject)}
                    </Badge>
                  ))}
                </div>

                <p className="mt-4 text-xs text-muted">
                  {!mentor.available
                    ? "Needs a model key on this deployment"
                    : !mentor.has_material
                      ? "No sources loaded — declines questions about them"
                      : mentor.sources.length > 0
                        ? `${mentor.sources.length} source${mentor.sources.length === 1 ? "" : "s"} on file`
                        : "Speaks from their own dossier"}
                </p>
                <p className="mt-3 text-xs font-medium text-indigo-700">Open profile →</p>
              </Link>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
