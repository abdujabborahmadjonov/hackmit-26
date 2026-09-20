import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type {
  ClassFormat,
  ClassProfile,
  ClassProfileInput,
  ClassStatus,
  CoursePlanSummary,
} from "../api/types";
import { CLASS_FORMATS, EDUCATION_LEVELS, SUBJECTS, humanize } from "../api/vocab";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Spinner,
} from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

const EMPTY_FORM: ClassProfileInput = {
  title: "",
  subject: "",
  level: "",
  format: "lecture",
  status: "planned",
  class_size: null,
  class_size_min: null,
  class_size_max: null,
  student_background: "",
  constraints: "",
  class_length_minutes: null,
  technology: "",
  notes: "",
};

function statusTone(status: ClassStatus): "indigo" | "emerald" | "amber" | "neutral" {
  if (status === "active") return "emerald";
  if (status === "planned") return "amber";
  return "neutral";
}

function sizeLabel(klass: ClassProfile): string {
  if (klass.class_size) return `${klass.class_size} students`;
  if (klass.class_size_min || klass.class_size_max) {
    return `${klass.class_size_min ?? "?"}–${klass.class_size_max ?? "?"} students`;
  }
  return "Size TBD";
}

export default function Classes() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<ClassProfile[]>([]);
  const [plans, setPlans] = useState<CoursePlanSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [composing, setComposing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ClassProfileInput>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [promotingId, setPromotingId] = useState<string | null>(null);
  const [promoteSize, setPromoteSize] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [classes, coursePlans] = await Promise.all([
        api.classProfiles({ limit: 50 }),
        api.coursePlans({ limit: 50 }),
      ]);
      setItems(classes.items);
      setPlans(coursePlans.items);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function setField<K extends keyof ClassProfileInput>(key: K, value: ClassProfileInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setComposing(true);
  }

  function openEdit(klass: ClassProfile) {
    setEditingId(klass.id);
    setForm({
      title: klass.title,
      subject: klass.subject,
      level: klass.level,
      format: klass.format,
      status: klass.status,
      class_size: klass.class_size ?? null,
      class_size_min: klass.class_size_min ?? null,
      class_size_max: klass.class_size_max ?? null,
      student_background: klass.student_background ?? "",
      constraints: klass.constraints ?? "",
      class_length_minutes: klass.class_length_minutes ?? null,
      technology: klass.technology ?? "",
      notes: klass.notes ?? "",
    });
    setComposing(true);
  }

  async function onSyllabus(file: File) {
    setExtracting(true);
    setError(null);
    try {
      const draft = await api.classFromDocument(file);
      setForm((current) => ({
        ...current,
        title: draft.title || current.title,
        subject: draft.subject || current.subject,
        level: draft.level || current.level,
        format: (draft.format as ClassFormat) || current.format,
        class_size: draft.class_size ?? current.class_size,
        class_size_min: draft.class_size_min ?? current.class_size_min,
        class_size_max: draft.class_size_max ?? current.class_size_max,
        student_background: draft.student_background || current.student_background,
        constraints: draft.constraints || current.constraints,
        class_length_minutes: draft.class_length_minutes ?? current.class_length_minutes,
        technology: draft.technology || current.technology,
        notes: draft.notes || current.notes,
      }));
      setComposing(true);
    } catch (err) {
      setError(err);
    } finally {
      setExtracting(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form.title.trim() || !form.subject.trim() || !form.level.trim()) return;
    setSaving(true);
    setError(null);
    const payload: ClassProfileInput = {
      ...form,
      title: form.title.trim(),
      subject: form.subject.trim(),
      level: form.level.trim(),
      student_background: form.student_background?.trim() || null,
      constraints: form.constraints?.trim() || null,
      technology: form.technology?.trim() || null,
      notes: form.notes?.trim() || null,
      class_size: form.class_size || null,
      class_size_min: form.class_size_min || null,
      class_size_max: form.class_size_max || null,
      class_length_minutes: form.class_length_minutes || null,
    };
    try {
      if (editingId) {
        const updated = await api.updateClassProfile(editingId, payload);
        setItems((current) => current.map((item) => (item.id === editingId ? updated : item)));
      } else {
        const created = await api.createClassProfile(payload);
        setItems((current) => [created, ...current]);
      }
      setComposing(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  async function promote(id: string) {
    const size = Number(promoteSize);
    if (!size || size < 1) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.promoteClassProfile(id, { class_size: size });
      setItems((current) => current.map((item) => (item.id === id ? updated : item)));
      setPromotingId(null);
      setPromoteSize("");
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this class profile?")) return;
    setDeletingId(id);
    try {
      await api.deleteClassProfile(id);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(err);
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <Loading label="Loading classes" />;

  return (
    <div>
      <PageHeader
        eyebrow="Your classrooms"
        title="Class profiles"
        description="Describe each class you teach so technique search and planning can match context — size, format, and constraints. Or generate a full class plan from the library."
        actions={
          <>
            <Link to="/classes/generate">
              <Button size="sm">Generate class</Button>
            </Link>
            <Button variant="secondary" size="sm" loading={extracting} onClick={() => fileRef.current?.click()}>
              Import syllabus
            </Button>
            <Button size="sm" variant="secondary" onClick={openCreate}>
              New class
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md,.markdown"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void onSyllabus(file);
                e.target.value = "";
              }}
            />
          </>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {plans.length > 0 && (
        <section className="mt-6">
          <div className="mb-3 flex items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-ink">Class plans</p>
              <p className="text-xs text-muted">
                Generated outlines grounded in resources and peer classes.
              </p>
            </div>
            <Link
              to="/classes/generate"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
            >
              New plan →
            </Link>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {plans.map((plan) => (
              <li key={plan.id}>
                <Link to={`/classes/plans/${plan.id}`}>
                  <Card className="h-full p-4" interactive>
                    <p className="font-semibold text-ink">{plan.title}</p>
                    <p className="mt-1 text-sm text-muted">
                      {humanize(plan.subject)} · {plan.duration_weeks} weeks ·{" "}
                      {plan.unit_count} units
                    </p>
                    <div className="mt-3">
                      <Badge tone="amber">{humanize(plan.status)}</Badge>
                    </div>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {composing && (
        <Card className="mt-6 p-5">
          <form onSubmit={save} className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <p className="font-semibold text-ink">{editingId ? "Edit class" : "New class"}</p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setComposing(false);
                  setEditingId(null);
                }}
              >
                Cancel
              </Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Title">
                <Input
                  value={form.title}
                  onChange={(e) => setField("title", e.target.value)}
                  placeholder="e.g. Calculus I — Fall section"
                  required
                  maxLength={200}
                />
              </Field>
              <Field label="Subject" hint="e.g. mathematics, biology">
                <Input
                  list="class-subjects"
                  value={form.subject}
                  onChange={(e) => setField("subject", e.target.value)}
                  placeholder="mathematics"
                  required
                  maxLength={80}
                />
                <datalist id="class-subjects">
                  {SUBJECTS.map((s) => (
                    <option key={s} value={s}>
                      {humanize(s)}
                    </option>
                  ))}
                </datalist>
              </Field>
              <Field label="Level" hint="e.g. high_school, university">
                <Input
                  list="class-levels"
                  value={form.level}
                  onChange={(e) => setField("level", e.target.value)}
                  placeholder="university"
                  required
                  maxLength={50}
                />
                <datalist id="class-levels">
                  {EDUCATION_LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {humanize(l)}
                    </option>
                  ))}
                </datalist>
              </Field>
              <Field label="Format">
                <Select
                  value={form.format}
                  onChange={(e) => setField("format", e.target.value as ClassFormat)}
                >
                  {CLASS_FORMATS.map((f) => (
                    <option key={f} value={f}>
                      {humanize(f)}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Class size" hint="Concrete size for active classes">
                <Input
                  type="number"
                  min={1}
                  max={1000}
                  value={form.class_size ?? ""}
                  onChange={(e) =>
                    setField("class_size", e.target.value ? Number(e.target.value) : null)
                  }
                />
              </Field>
              <Field label="Size min" hint="Optional range when planned">
                <Input
                  type="number"
                  min={1}
                  max={1000}
                  value={form.class_size_min ?? ""}
                  onChange={(e) =>
                    setField("class_size_min", e.target.value ? Number(e.target.value) : null)
                  }
                />
              </Field>
              <Field label="Size max">
                <Input
                  type="number"
                  min={1}
                  max={1000}
                  value={form.class_size_max ?? ""}
                  onChange={(e) =>
                    setField("class_size_max", e.target.value ? Number(e.target.value) : null)
                  }
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Session length (minutes)">
                <Input
                  type="number"
                  min={1}
                  max={600}
                  value={form.class_length_minutes ?? ""}
                  onChange={(e) =>
                    setField("class_length_minutes", e.target.value ? Number(e.target.value) : null)
                  }
                />
              </Field>
              <Field label="Technology">
                <Input
                  value={form.technology ?? ""}
                  onChange={(e) => setField("technology", e.target.value)}
                  placeholder="LMS, clickers, lab benches…"
                />
              </Field>
            </div>

            <Field label="Student background">
              <textarea
                className={TEXTAREA}
                rows={2}
                value={form.student_background ?? ""}
                onChange={(e) => setField("student_background", e.target.value)}
                placeholder="Prerequisites, majors, prior experience…"
              />
            </Field>
            <Field label="Constraints">
              <textarea
                className={TEXTAREA}
                rows={2}
                value={form.constraints ?? ""}
                onChange={(e) => setField("constraints", e.target.value)}
                placeholder="Room layout, time limits, accessibility needs…"
              />
            </Field>
            <Field label="Notes">
              <textarea
                className={TEXTAREA}
                rows={2}
                value={form.notes ?? ""}
                onChange={(e) => setField("notes", e.target.value)}
              />
            </Field>

            <Button type="submit" loading={saving}>
              {editingId ? "Save changes" : "Create class"}
            </Button>
          </form>
        </Card>
      )}

      {items.length === 0 && !composing ? (
        <div className="mt-7">
          <EmptyState
            title="No class profiles yet"
            body="Generate a class plan from the library, add a class you teach, or import a syllabus."
            action={
              <div className="flex flex-wrap gap-2">
                <Link to="/classes/generate">
                  <Button>Generate class</Button>
                </Link>
                <Button variant="secondary" onClick={openCreate}>
                  New class
                </Button>
              </div>
            }
          />
        </div>
      ) : (
        <ul className="mt-7 grid gap-4 sm:grid-cols-2">
          {items.map((klass) => (
            <li key={klass.id}>
              <Card className="flex h-full flex-col p-5" interactive>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{klass.title}</p>
                    <p className="mt-1 text-sm text-muted">
                      {humanize(klass.subject)} · {humanize(klass.level)} · {humanize(klass.format)}
                    </p>
                  </div>
                  <Badge tone={statusTone(klass.status)}>{humanize(klass.status)}</Badge>
                </div>
                <p className="mt-3 text-xs text-muted">{sizeLabel(klass)}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link
                    to={`/classes/${klass.id}/search`}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    Find techniques →
                  </Link>
                  <Link
                    to={`/classes/${klass.id}/planning`}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    Plan ahead →
                  </Link>
                  <Link
                    to={`/classes/generate?classId=${klass.id}`}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    Generate class →
                  </Link>
                </div>
                <div className="mt-auto flex flex-wrap gap-2 pt-4">
                  <Button size="sm" variant="secondary" onClick={() => openEdit(klass)}>
                    Edit
                  </Button>
                  {klass.status === "planned" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setPromotingId(klass.id);
                        setPromoteSize(String(klass.class_size ?? klass.class_size_max ?? ""));
                      }}
                    >
                      Promote to active
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    loading={deletingId === klass.id}
                    onClick={() => void remove(klass.id)}
                  >
                    Delete
                  </Button>
                </div>
                {promotingId === klass.id && (
                  <div className="mt-4 rounded-xl bg-slate-50 p-3">
                    <p className="text-sm font-medium text-ink">Concrete class size</p>
                    <p className="mt-1 text-xs text-muted">
                      Promoting planned → active needs a real enrollment number.
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Input
                        type="number"
                        min={1}
                        max={1000}
                        value={promoteSize}
                        onChange={(e) => setPromoteSize(e.target.value)}
                        placeholder="e.g. 28"
                      />
                      <Button size="sm" loading={saving} onClick={() => void promote(klass.id)}>
                        Promote
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setPromotingId(null);
                          setPromoteSize("");
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}

      {extracting && (
        <div className="fixed inset-x-0 bottom-20 z-30 mx-auto flex w-fit items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm text-white shadow-lg md:bottom-6">
          <Spinner className="h-4 w-4" />
          Reading syllabus…
        </div>
      )}
    </div>
  );
}
