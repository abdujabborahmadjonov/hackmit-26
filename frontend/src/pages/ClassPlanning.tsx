import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ClassProfile, PlanningResponse, Technique } from "../api/types";
import { humanize } from "../api/vocab";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  Loading,
  PageHeader,
  Stars,
} from "../components/ui";

function MiniTechnique({ tech }: { tech: Technique }) {
  const avg = tech.rating_summary?.average ?? tech.average_rating;
  const count = tech.rating_summary?.count ?? tech.rating_count;
  return (
    <Link
      to={`/techniques/${tech.id}`}
      className="block rounded-xl bg-white p-3 ring-1 ring-line transition hover:ring-slate-300"
    >
      <p className="font-medium text-ink">{tech.title}</p>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{tech.summary}</p>
      {count > 0 && (
        <p className="mt-2">
          <Stars value={avg} count={count} />
        </p>
      )}
    </Link>
  );
}

export default function ClassPlanning() {
  const { classId = "" } = useParams();
  const [klass, setKlass] = useState<ClassProfile | null>(null);
  const [conceptLabel, setConceptLabel] = useState("");
  const [result, setResult] = useState<PlanningResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.classProfile(classId);
        if (!cancelled) setKlass(data);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classId]);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!conceptLabel.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api.planningMode({
        class_profile_id: classId,
        concept_label: conceptLabel.trim(),
      });
      setResult(data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label="Loading class" />;
  if (!klass) {
    return (
      <div>
        <ErrorNote error={error ?? new Error("Class not found")} />
        <Link to="/classes" className="mt-4 inline-block text-sm font-semibold text-indigo-600">
          ← Back to classes
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow={klass.title}
        title="Planning mode"
        description="Enter a concept before you teach it. See common pitfalls peers report, and the techniques that helped most."
        actions={
          <Link to={`/classes/${classId}/search`}>
            <Button size="sm" variant="secondary">
              Technique search
            </Button>
          </Link>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      <Card className="mt-6 p-5">
        <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Field label="Concept">
              <Input
                value={conceptLabel}
                onChange={(e) => setConceptLabel(e.target.value)}
                placeholder="e.g. Related rates"
                required
                maxLength={200}
              />
            </Field>
          </div>
          <Button type="submit" loading={busy}>
            Show pitfalls
          </Button>
        </form>
      </Card>

      {result && (
        <div className="mt-8 space-y-5">
          {result.concept && (
            <p className="text-sm text-muted">
              Concept:{" "}
              <span className="font-semibold text-ink">{result.concept.label}</span>
              {result.concept.subject ? ` · ${humanize(result.concept.subject)}` : ""}
            </p>
          )}

          {result.pitfalls.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="font-semibold text-ink">No common pitfalls yet</p>
              <p className="mt-2 text-sm text-muted">
                As more teachers rate techniques for this concept, patterns will show up here.
              </p>
            </Card>
          ) : (
            result.pitfalls.map((pitfall) => (
              <Card key={pitfall.problem_type} className="p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="amber">{humanize(pitfall.problem_type)}</Badge>
                  <p className="font-semibold text-ink">{pitfall.label}</p>
                  <span className="text-xs text-muted">
                    {pitfall.report_count} report{pitfall.report_count === 1 ? "" : "s"}
                  </span>
                </div>
                {pitfall.top_techniques.length > 0 ? (
                  <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                    {pitfall.top_techniques.map((tech) => (
                      <li key={tech.id}>
                        <MiniTechnique tech={tech} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-muted">No top techniques linked yet.</p>
                )}
              </Card>
            ))
          )}
        </div>
      )}

      <p className="mt-8">
        <Link to="/classes" className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
          ← Back to classes
        </Link>
      </p>
    </div>
  );
}
