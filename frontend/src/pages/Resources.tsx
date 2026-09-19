import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RecommendedResource, Resource } from "../api/types";
import { EDUCATION_LEVELS, SUBJECTS, humanize } from "../api/vocab";
import { Badge, Button, Card, ErrorNote, Input, Loading, PageHeader, Select, cx } from "../components/ui";

function ResourceRow({ resource, score, reasons }: { resource: Resource; score?: number; reasons?: string[] }) {
  return (
    <Card className="flex h-full flex-col p-5" interactive>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
            <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M7 3h7l4 4v14H7V3Z" />
              <path d="M14 3v5h5M10 13h5M10 17h5" />
            </svg>
          </span>
          <div className="min-w-0">
          <p className="font-semibold text-ink">{resource.title}</p>
          {resource.description && (
            <p className="mt-1 line-clamp-2 text-sm leading-5 text-muted">{resource.description}</p>
          )}
          </div>
        </div>
        {score !== undefined && (
          <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
            {Math.round(score * 100)}% fit
          </span>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {resource.subject && <Badge tone="emerald">{humanize(resource.subject)}</Badge>}
        {resource.education_level && <Badge tone="amber">{humanize(resource.education_level)}</Badge>}
        {resource.teaching_method && <Badge tone="indigo">{humanize(resource.teaching_method)}</Badge>}
        {resource.difficulty && <Badge>{humanize(resource.difficulty)}</Badge>}
        {resource.file_url && (
          <a
            href={resource.file_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
          >
            Download
          </a>
        )}
      </div>
      {reasons && reasons.length > 0 && (
        <ul className="mt-4 space-y-1.5 rounded-xl bg-slate-50 p-3">
          {reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-xs leading-5 text-muted">
              <span className="text-emerald-600">✓</span> {reason}
            </li>
          ))}
        </ul>
      )}
      <Link
        to={`/teachers/${resource.owner_id}`}
        className="mt-auto inline-block pt-4 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
      >
        View the educator who made this →
      </Link>
    </Card>
  );
}

export default function Resources() {
  const [tab, setTab] = useState<"foryou" | "browse">("foryou");
  const [recommended, setRecommended] = useState<RecommendedResource[]>([]);
  const [browse, setBrowse] = useState<{ resource: Resource; score: number }[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [subject, setSubject] = useState("");
  const [level, setLevel] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const loadRecommended = useCallback(async () => {
    setLoading(true);
    try {
      setRecommended(await api.recommendedResources(8));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBrowse = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.resources({
        query: query || undefined,
        subject: subject || undefined,
        education_level: level || undefined,
        sort: query ? "relevance" : "newest",
        limit: 20,
      });
      setBrowse(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [query, subject, level]);

  useEffect(() => {
    if (tab === "foryou") void loadRecommended();
    else void loadBrowse();
  }, [tab, loadRecommended, loadBrowse]);

  return (
    <div>
      <PageHeader
        eyebrow="Community library"
        title="Resources built by educators"
        description="Discover lesson plans, project briefs, assessments, and classroom-ready ideas—ranked by how well they fit your teaching context."
      />

      <div className="mt-7 inline-flex gap-1 rounded-xl bg-slate-100 p-1">
        {(
          [
            ["foryou", "Picked for you"],
            ["browse", "Browse all"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cx(
              "rounded-lg px-5 py-2 text-sm font-medium transition",
              tab === key ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "browse" && (
        <Card className="mt-5 grid gap-3 p-5 sm:grid-cols-4">
          <div className="sm:col-span-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by meaning, e.g. teaching recursion with games"
              onKeyDown={(e) => e.key === "Enter" && void loadBrowse()}
            />
          </div>
          <Select value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">Any subject</option>
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </Select>
          <div className="flex gap-2">
            <Select value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">Any level</option>
              {EDUCATION_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {humanize(l)}
                </option>
              ))}
            </Select>
            <Button onClick={() => void loadBrowse()}>Go</Button>
          </div>
        </Card>
      )}

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {loading ? (
        <Loading />
      ) : tab === "foryou" ? (
        <div className="stagger mt-5 grid gap-4 md:grid-cols-2">
          {recommended.map((item) => (
            <ResourceRow
              key={item.resource.id}
              resource={item.resource}
              score={item.match_score}
              reasons={item.reasons}
            />
          ))}
          {recommended.length === 0 && (
            <Card className="p-10 text-center text-sm text-muted">
              Nothing yet — add subjects to your profile and these will fill in.
            </Card>
          )}
        </div>
      ) : (
        <>
          <p className="mt-5 text-xs font-medium text-muted">{total.toLocaleString()} resources found</p>
          <div className="stagger mt-3 grid gap-4 md:grid-cols-2">
            {browse.map(({ resource, score }) => (
              <ResourceRow key={resource.id} resource={resource} score={query ? score : undefined} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
