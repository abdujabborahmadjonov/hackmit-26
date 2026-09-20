import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ClassProfile, RatingLink, Technique } from "../api/types";
import { humanize } from "../api/vocab";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Loading,
  PageHeader,
  Select,
  Stars,
} from "../components/ui";

function distributionBars(distribution: Record<string, number>, total: number) {
  return [5, 4, 3, 2, 1].map((star) => {
    const count = distribution[String(star)] ?? 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    return { star, count, pct };
  });
}

function qrDataUrl(text: string): string {
  return `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(text)}`;
}

export default function TechniqueDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [tech, setTech] = useState<Technique | null>(null);
  const [classes, setClasses] = useState<ClassProfile[]>([]);
  const [classId, setClassId] = useState("");
  const [link, setLink] = useState<RatingLink | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"ask" | "tried" | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [technique, profiles] = await Promise.all([
          api.technique(id),
          api.classProfiles({ limit: 50 }),
        ]);
        if (cancelled) return;
        setTech(technique);
        setClasses(profiles.items);
        const active = profiles.items.find((c) => c.status === "active");
        setClassId(active?.id ?? profiles.items[0]?.id ?? "");
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function askTeacher() {
    if (!tech) return;
    setBusy("ask");
    setError(null);
    try {
      await api.startConversation(
        tech.owner_id,
        `Hi — I saw your technique "${tech.title}" and would love to hear how it worked in your class.`,
      );
      navigate("/messages");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function triedThis() {
    if (!tech || !classId) return;
    setBusy("tried");
    setError(null);
    setLink(null);
    try {
      const created = await api.triedThis(tech.id, {
        class_profile_id: classId,
        label: `Tried: ${tech.title.slice(0, 80)}`,
      });
      setLink(created);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function copyRateUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  if (loading) return <Loading label="Loading technique" />;
  if (!tech) {
    return (
      <div>
        <ErrorNote error={error ?? new Error("Technique not found")} />
        <Link to="/classes" className="mt-4 inline-block text-sm font-semibold text-indigo-600">
          ← Back to classes
        </Link>
      </div>
    );
  }

  const summary = tech.rating_summary;
  const ownerName = tech.owner
    ? `${tech.owner.first_name} ${tech.owner.last_name}`
    : "Educator";
  const rateUrl =
    link?.token
      ? `${window.location.origin}/rate/${link.token}`
      : link?.rate_path
        ? `${window.location.origin}${link.rate_path.startsWith("/") ? "" : "/"}${link.rate_path}`
        : null;
  const bars = distributionBars(summary?.distribution ?? {}, summary?.count ?? tech.rating_count);

  return (
    <div>
      <PageHeader
        eyebrow="Technique"
        title={tech.title}
        description={tech.summary}
        actions={
          <>
            <Button size="sm" loading={busy === "ask"} onClick={() => void askTeacher()}>
              Ask this teacher
            </Button>
            <Link to={`/teachers/${tech.owner_id}`}>
              <Button size="sm" variant="secondary">
                View profile
              </Button>
            </Link>
          </>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card className="space-y-5 p-5">
          <div className="flex flex-wrap gap-1.5">
            {tech.problem_types.map((ptype) => (
              <Badge key={ptype} tone="amber">
                {humanize(ptype)}
              </Badge>
            ))}
            {tech.concepts.map((c) => (
              <Badge key={c.id} tone="indigo">
                {c.label}
              </Badge>
            ))}
            {tech.class_time_minutes && (
              <Badge>{tech.class_time_minutes} min</Badge>
            )}
            {tech.teaching_style && <Badge>{humanize(tech.teaching_style)}</Badge>}
          </div>

          <div>
            <h2 className="text-sm font-semibold text-ink">Steps</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">{tech.steps}</p>
          </div>

          {tech.materials && (
            <div>
              <h2 className="text-sm font-semibold text-ink">Materials</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">
                {tech.materials}
              </p>
            </div>
          )}

          {(tech.context_subject || tech.context_level || tech.context_format) && (
            <div className="rounded-xl bg-slate-50 p-4 text-sm text-muted">
              <p className="font-semibold text-ink">Original context</p>
              <p className="mt-1">
                {[tech.context_subject, tech.context_level, tech.context_format]
                  .filter(Boolean)
                  .map((v) => humanize(v))
                  .join(" · ")}
                {tech.context_class_size ? ` · ${tech.context_class_size} students` : ""}
              </p>
              {tech.context_notes && <p className="mt-2">{tech.context_notes}</p>}
            </div>
          )}

          <p className="text-xs text-muted">Shared by {ownerName}</p>
        </Card>

        <div className="space-y-5">
          <Card className="p-5">
            <p className="text-sm font-semibold text-ink">Student ratings</p>
            {(summary?.count ?? tech.rating_count) > 0 ? (
              <>
                <div className="mt-3">
                  <Stars
                    value={summary?.average ?? tech.average_rating}
                    count={summary?.count ?? tech.rating_count}
                  />
                </div>
                {summary && summary.similar_class_count > 0 && (
                  <p className="mt-1 text-xs text-muted">
                    Includes feedback from {summary.similar_class_count} similar class
                    {summary.similar_class_count === 1 ? "" : "es"}
                  </p>
                )}
                {summary?.sample_comment && (
                  <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm italic text-muted">
                    “{summary.sample_comment}”
                  </p>
                )}
                <ul className="mt-4 space-y-2">
                  {bars.map(({ star, count, pct }) => (
                    <li key={star} className="flex items-center gap-2 text-xs text-muted">
                      <span className="w-6">{star}★</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-amber-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-8 text-right">{count}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="mt-2 text-sm text-muted">No student ratings yet.</p>
            )}
          </Card>

          <Card className="p-5">
            <p className="text-sm font-semibold text-ink">I tried this</p>
            <p className="mt-1 text-xs text-muted">
              Pick your class to create a short-lived student rating link (token + QR).
            </p>
            <div className="mt-3 space-y-3">
              <Field label="Class">
                <Select value={classId} onChange={(e) => setClassId(e.target.value)}>
                  <option value="">Select a class</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title} ({humanize(c.status)})
                    </option>
                  ))}
                </Select>
              </Field>
              <Button
                size="sm"
                loading={busy === "tried"}
                disabled={!classId}
                onClick={() => void triedThis()}
              >
                Create rating link
              </Button>
            </div>

            {link && rateUrl && (
              <div className="mt-4 rounded-xl bg-indigo-50/70 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
                  Share with students
                </p>
                <p className="mt-2 break-all text-sm text-ink">{rateUrl}</p>
                {link.token && (
                  <p className="mt-1 text-xs text-muted">Token: {link.token}</p>
                )}
                <div className="mt-3 flex flex-wrap items-start gap-4">
                  <img
                    src={qrDataUrl(rateUrl)}
                    alt="QR code for rating link"
                    width={160}
                    height={160}
                    className="rounded-lg bg-white p-2 ring-1 ring-line"
                  />
                  <Button size="sm" variant="secondary" onClick={() => void copyRateUrl(rateUrl)}>
                    {copied ? "Copied" : "Copy URL"}
                  </Button>
                </div>
                <p className="mt-2 text-xs text-muted">
                  Expires {new Date(link.expires_at).toLocaleString()}
                  {link.max_uses != null ? ` · max ${link.max_uses} uses` : ""}
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
