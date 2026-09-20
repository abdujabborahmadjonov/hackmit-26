import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  CoursePlan,
  CoursePlanItemRole,
  CoursePlanStructureInput,
  CoursePlanUnit,
} from "../api/types";
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
  Spinner,
} from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

function toStructure(plan: CoursePlan): CoursePlanStructureInput {
  return {
    overview: plan.overview,
    units: plan.units.map((unit) => ({
      title: unit.title,
      objectives: unit.objectives,
      concept_labels: unit.concept_labels,
      sessions: unit.sessions.map((session) => ({
        title: session.title,
        focus: session.focus,
        activities_summary: session.activities_summary,
        items: session.items.map((item) => ({
          role: item.role,
          resource_id: item.resource_id,
          technique_id: item.technique_id,
        })),
      })),
    })),
  };
}

function cloneUnits(units: CoursePlanUnit[]): CoursePlanUnit[] {
  return structuredClone(units);
}

export default function CoursePlanDetail() {
  const { planId = "" } = useParams();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<CoursePlan | null>(null);
  const [units, setUnits] = useState<CoursePlanUnit[]>([]);
  const [overview, setOverview] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [regenBusy, setRegenBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.coursePlan(planId);
      setPlan(data);
      setUnits(cloneUnits(data.units));
      setOverview(data.overview ?? "");
      setTitle(data.title);
      setDirty(false);
      setEditing(false);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [planId]);

  useEffect(() => {
    void load();
  }, [load]);

  function markDirty(nextUnits: CoursePlanUnit[]) {
    setUnits(nextUnits);
    setDirty(true);
  }

  function updateUnit(index: number, patch: Partial<CoursePlanUnit>) {
    const next = cloneUnits(units);
    next[index] = { ...next[index], ...patch };
    markDirty(next);
  }

  function updateSession(
    unitIndex: number,
    sessionIndex: number,
    patch: Partial<CoursePlanUnit["sessions"][number]>,
  ) {
    const next = cloneUnits(units);
    next[unitIndex].sessions[sessionIndex] = {
      ...next[unitIndex].sessions[sessionIndex],
      ...patch,
    };
    markDirty(next);
  }

  async function saveEdits() {
    if (!plan) return;
    setSaving(true);
    setError(null);
    try {
      if (title.trim() && title.trim() !== plan.title) {
        await api.updateCoursePlan(plan.id, { title: title.trim() });
      }
      const updated = await api.updateCoursePlanStructure(plan.id, {
        overview: overview || null,
        units: toStructure({ ...plan, units, overview }).units,
      });
      setPlan(updated);
      setUnits(cloneUnits(updated.units));
      setOverview(updated.overview ?? "");
      setTitle(updated.title);
      setDirty(false);
      setEditing(false);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  async function regenerateAll() {
    if (!plan) return;
    setRegenBusy("all");
    setError(null);
    try {
      const updated = await api.regenerateCoursePlan(plan.id);
      setPlan(updated);
      setUnits(cloneUnits(updated.units));
      setOverview(updated.overview ?? "");
      setTitle(updated.title);
      setDirty(false);
      setEditing(false);
    } catch (err) {
      setError(err);
    } finally {
      setRegenBusy(null);
    }
  }

  async function regenerateUnit(unitId: string) {
    if (!plan) return;
    setRegenBusy(unitId);
    setError(null);
    try {
      const updated = await api.regenerateCoursePlanUnit(plan.id, unitId);
      setPlan(updated);
      setUnits(cloneUnits(updated.units));
      setOverview(updated.overview ?? "");
      setDirty(false);
      setEditing(false);
    } catch (err) {
      setError(err);
    } finally {
      setRegenBusy(null);
    }
  }

  async function removePlan() {
    if (!plan || !confirm("Delete this course plan?")) return;
    try {
      await api.deleteCoursePlan(plan.id);
      navigate("/classes");
    } catch (err) {
      setError(err);
    }
  }

  if (loading) return <Loading label="Loading course plan" />;
  if (!plan) {
    return (
      <div>
        <ErrorNote error={error} />
        <Link to="/classes" className="mt-4 inline-block text-sm font-semibold text-indigo-600">
          ← Back to classes
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Course plan"
        title={editing ? "Edit course plan" : plan.title}
        description={`${humanize(plan.subject)} · ${humanize(plan.level)} · ${plan.duration_weeks} weeks · ${plan.sessions_per_week}× / week`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to="/classes"
              className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
            >
              ← Classes
            </Link>
            {plan.class_profile_id && (
              <Link
                to={`/classes/${plan.class_profile_id}/planning`}
                className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
              >
                Class planning →
              </Link>
            )}
          </div>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Badge tone="amber">{humanize(plan.status)}</Badge>
        <Badge tone="neutral">{plan.units.length} units</Badge>
        {plan.similar_classes.length > 0 && (
          <Badge tone="indigo">Inspired by {plan.similar_classes.length} peer classes</Badge>
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {!editing ? (
          <>
            <Button size="sm" onClick={() => setEditing(true)}>
              Edit manually
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={regenBusy === "all"}
              onClick={() => void regenerateAll()}
            >
              Regenerate plan
            </Button>
            <Button size="sm" variant="danger" onClick={() => void removePlan()}>
              Delete
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" loading={saving} disabled={!dirty && title === plan.title} onClick={() => void saveEdits()}>
              Save changes
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setUnits(cloneUnits(plan.units));
                setOverview(plan.overview ?? "");
                setTitle(plan.title);
                setDirty(false);
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </>
        )}
      </div>

      {editing && (
        <Card className="mt-5 space-y-3 p-5">
          <Field label="Title">
            <Input value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} maxLength={200} />
          </Field>
          <Field label="Overview">
            <textarea
              className={TEXTAREA}
              rows={3}
              value={overview}
              onChange={(e) => {
                setOverview(e.target.value);
                setDirty(true);
              }}
            />
          </Field>
        </Card>
      )}

      {!editing && plan.overview && (
        <Card className="mt-5 p-5">
          <p className="text-sm font-semibold text-ink">Overview</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">{plan.overview}</p>
        </Card>
      )}

      {plan.similar_classes.length > 0 && !editing && (
        <Card className="mt-4 p-5">
          <p className="text-sm font-semibold text-ink">Peer class inspiration</p>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {plan.similar_classes.map((c) => (
              <li key={c.id}>
                {c.title} · {humanize(c.subject)} · {humanize(c.level)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <ul className="mt-6 space-y-4">
        {units.map((unit, unitIndex) => (
          <li key={unit.id}>
            <Card className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {editing ? (
                    <Input
                      value={unit.title}
                      onChange={(e) => updateUnit(unitIndex, { title: e.target.value })}
                    />
                  ) : (
                    <p className="font-semibold text-ink">
                      Unit {unitIndex + 1}: {unit.title}
                    </p>
                  )}
                  {editing ? (
                    <textarea
                      className={`${TEXTAREA} mt-2`}
                      rows={2}
                      value={unit.objectives ?? ""}
                      onChange={(e) => updateUnit(unitIndex, { objectives: e.target.value })}
                      placeholder="Objectives"
                    />
                  ) : (
                    unit.objectives && (
                      <p className="mt-2 text-sm text-muted">{unit.objectives}</p>
                    )
                  )}
                  {unit.concept_labels.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {unit.concept_labels.map((label) => (
                        <Badge key={label} tone="neutral">
                          {label}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                {!editing && (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={regenBusy === unit.id}
                    onClick={() => void regenerateUnit(unit.id)}
                  >
                    Regenerate unit
                  </Button>
                )}
              </div>

              <ul className="mt-4 space-y-3">
                {unit.sessions.map((session, sessionIndex) => (
                  <li
                    key={session.id}
                    className="rounded-xl bg-slate-50 p-3 ring-1 ring-line/70"
                  >
                    {editing ? (
                      <Input
                        value={session.title}
                        onChange={(e) =>
                          updateSession(unitIndex, sessionIndex, { title: e.target.value })
                        }
                      />
                    ) : (
                      <p className="text-sm font-medium text-ink">{session.title}</p>
                    )}
                    {editing ? (
                      <textarea
                        className={`${TEXTAREA} mt-2`}
                        rows={2}
                        value={session.focus ?? ""}
                        onChange={(e) =>
                          updateSession(unitIndex, sessionIndex, { focus: e.target.value })
                        }
                        placeholder="Focus"
                      />
                    ) : (
                      session.focus && (
                        <p className="mt-1 text-xs text-muted">{session.focus}</p>
                      )
                    )}
                    {session.activities_summary && !editing && (
                      <p className="mt-1 text-xs leading-5 text-muted">
                        {session.activities_summary}
                      </p>
                    )}
                    <ul className="mt-2 space-y-1">
                      {session.items.map((item) => (
                        <li key={item.id} className="text-xs text-muted">
                          <span className="font-semibold text-ink">
                            {humanize(item.role as CoursePlanItemRole)}
                          </span>
                          {item.resource_id && (
                            <>
                              {" · "}
                              <Link
                                to="/resources"
                                className="font-medium text-indigo-600 hover:text-indigo-700"
                              >
                                {item.resource_title ?? "Resource"}
                              </Link>
                            </>
                          )}
                          {item.technique_id && (
                            <>
                              {" · "}
                              <Link
                                to={`/techniques/${item.technique_id}`}
                                className="font-medium text-indigo-600 hover:text-indigo-700"
                              >
                                {item.technique_title ?? "Technique"}
                              </Link>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                    {editing && (
                      <p className="mt-2 text-[11px] text-muted">
                        Resource/technique links are preserved on save. Use regenerate to
                        re-pick library items for this unit.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          </li>
        ))}
      </ul>

      {regenBusy && (
        <div className="fixed inset-x-0 bottom-20 z-30 mx-auto flex w-fit items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm text-white shadow-lg md:bottom-6">
          <Spinner className="h-4 w-4" />
          Regenerating…
        </div>
      )}
    </div>
  );
}
