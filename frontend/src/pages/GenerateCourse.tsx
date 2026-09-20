import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ClassFormat, ClassProfile, CoursePlanGenerateInput } from "../api/types";
import { CLASS_FORMATS, EDUCATION_LEVELS, SUBJECTS, humanize } from "../api/vocab";
import {
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
} from "../components/ui";

const TEXTAREA =
  "w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-ink ring-1 ring-line " +
  "placeholder:text-slate-400 hover:ring-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500";

type Step = 1 | 2 | 3;

const EMPTY: CoursePlanGenerateInput = {
  title: "",
  subject: "mathematics",
  level: "university",
  format: "lecture",
  duration_weeks: 12,
  sessions_per_week: 2,
  class_size: null,
  class_size_min: null,
  class_size_max: null,
  class_length_minutes: 50,
  goals: "",
  constraints: "",
  student_background: "",
  technology: "",
  notes: "",
  topic_hints: [],
  class_profile_id: null,
};

export default function GenerateCourse() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const existingClassId = params.get("classId");

  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState<CoursePlanGenerateInput>(EMPTY);
  const [topicText, setTopicText] = useState("");
  const [classes, setClasses] = useState<ClassProfile[]>([]);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [status, page] = await Promise.all([
          api.aiStatus(),
          api.classProfiles({ limit: 50 }),
        ]);
        setAiEnabled(status.enabled && status.features.includes("course_plan_generate"));
        setClasses(page.items);
        if (existingClassId) {
          const match = page.items.find((c) => c.id === existingClassId);
          if (match) {
            setForm((current) => ({
              ...current,
              title: match.title,
              subject: match.subject,
              level: match.level,
              format: match.format,
              class_size: match.class_size ?? null,
              class_size_min: match.class_size_min ?? null,
              class_size_max: match.class_size_max ?? null,
              class_length_minutes: match.class_length_minutes ?? 50,
              constraints: match.constraints ?? "",
              student_background: match.student_background ?? "",
              technology: match.technology ?? "",
              notes: match.notes ?? "",
              class_profile_id: match.id,
            }));
          }
        }
      } catch (err) {
        setError(err);
      }
    })();
  }, [existingClassId]);

  const topicHints = useMemo(
    () =>
      topicText
        .split(/[\n,]/)
        .map((t) => t.trim())
        .filter(Boolean),
    [topicText],
  );

  function setField<K extends keyof CoursePlanGenerateInput>(
    key: K,
    value: CoursePlanGenerateInput[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function canAdvance(from: Step): boolean {
    if (from === 1) {
      return Boolean(form.title.trim() && form.subject && form.level && form.format);
    }
    if (from === 2) {
      return form.duration_weeks >= 1 && (form.sessions_per_week ?? 1) >= 1;
    }
    return true;
  }

  async function runGenerate() {
    if (generating) return;
    if (!aiEnabled) {
      setError(new Error("Class plan generation is not configured on this deployment."));
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const plan = await api.generateCoursePlan({
        ...form,
        topic_hints: topicHints,
        goals: form.goals || null,
        constraints: form.constraints || null,
        student_background: form.student_background || null,
        technology: form.technology || null,
        notes: form.notes || null,
      });
      navigate(`/classes/plans/${plan.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Classes"
        title="Generate a class"
        description="Describe the class you want to teach. EduMatch builds a multi-week plan grounded in existing resources, techniques, and similar peer classes."
        actions={
          <Link to="/classes" className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
            ← Back to classes
          </Link>
        }
      />

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {!aiEnabled && (
        <Card className="mt-4 border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Generative features are off on this deployment (no LLM key). You can still browse
          existing plans, but new generation will fail until the API is configured.
        </Card>
      )}

      <div className="mt-6 flex gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={
              step === n
                ? "rounded-full bg-indigo-600 px-3 py-1 text-white"
                : "rounded-full bg-slate-100 px-3 py-1"
            }
          >
            Step {n}
          </span>
        ))}
      </div>

      <Card className="mt-4 p-5">
        {/* Prevent Enter-in-input from submitting early; generate only via the step-3 button. */}
        <form
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
          }}
          className="space-y-4"
        >          {step === 1 && (
            <>
              <p className="font-semibold text-ink">What are you teaching?</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Class title">
                  <Input
                    value={form.title}
                    onChange={(e) => setField("title", e.target.value)}
                    placeholder="e.g. Intro to Statistics"
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Attach to existing class" hint="Optional — otherwise a planned class is created">
                  <Select
                    value={form.class_profile_id ?? ""}
                    onChange={(e) => {
                      const id = e.target.value || null;
                      setField("class_profile_id", id);
                      const match = classes.find((c) => c.id === id);
                      if (match) {
                        setForm((current) => ({
                          ...current,
                          class_profile_id: match.id,
                          title: current.title || match.title,
                          subject: match.subject,
                          level: match.level,
                          format: match.format,
                        }));
                      }
                    }}
                  >
                    <option value="">Create a new planned class</option>
                    {classes.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Subject">
                  <Select
                    value={form.subject}
                    onChange={(e) => setField("subject", e.target.value)}
                    required
                  >
                    {SUBJECTS.map((s) => (
                      <option key={s} value={s}>
                        {humanize(s)}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Education level">
                  <Select
                    value={form.level}
                    onChange={(e) => setField("level", e.target.value)}
                    required
                  >
                    {EDUCATION_LEVELS.map((l) => (
                      <option key={l} value={l}>
                        {humanize(l)}
                      </option>
                    ))}
                  </Select>
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
                <Field label="Session length (minutes)">
                  <Input
                    type="number"
                    min={1}
                    max={600}
                    value={form.class_length_minutes ?? ""}
                    onChange={(e) =>
                      setField(
                        "class_length_minutes",
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                  />
                </Field>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <p className="font-semibold text-ink">Size, duration, and constraints</p>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Duration (weeks)">
                  <Input
                    type="number"
                    min={1}
                    max={52}
                    value={form.duration_weeks}
                    onChange={(e) => setField("duration_weeks", Number(e.target.value) || 1)}
                    required
                  />
                </Field>
                <Field label="Sessions per week">
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={form.sessions_per_week ?? 1}
                    onChange={(e) =>
                      setField("sessions_per_week", Number(e.target.value) || 1)
                    }
                    required
                  />
                </Field>
                <Field label="Class size">
                  <Input
                    type="number"
                    min={1}
                    max={1000}
                    value={form.class_size ?? ""}
                    onChange={(e) =>
                      setField("class_size", e.target.value ? Number(e.target.value) : null)
                    }
                    placeholder="e.g. 30"
                  />
                </Field>
                <Field label="Size min">
                  <Input
                    type="number"
                    min={1}
                    max={1000}
                    value={form.class_size_min ?? ""}
                    onChange={(e) =>
                      setField(
                        "class_size_min",
                        e.target.value ? Number(e.target.value) : null,
                      )
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
                      setField(
                        "class_size_max",
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                  />
                </Field>
              </div>
              <Field label="Constraints" hint="Room, tech limits, pacing rules…">
                <textarea
                  className={TEXTAREA}
                  rows={3}
                  value={form.constraints ?? ""}
                  onChange={(e) => setField("constraints", e.target.value)}
                  maxLength={4000}
                />
              </Field>
              <Field label="Technology available">
                <Input
                  value={form.technology ?? ""}
                  onChange={(e) => setField("technology", e.target.value)}
                  placeholder="projector, LMS, lab kits…"
                  maxLength={2000}
                />
              </Field>
              <Field label="Student background">
                <textarea
                  className={TEXTAREA}
                  rows={2}
                  value={form.student_background ?? ""}
                  onChange={(e) => setField("student_background", e.target.value)}
                  maxLength={4000}
                />
              </Field>
            </>
          )}

          {step === 3 && (
            <>
              <p className="font-semibold text-ink">Goals and topics</p>
              <Field label="Learning goals">
                <textarea
                  className={TEXTAREA}
                  rows={4}
                  value={form.goals ?? ""}
                  onChange={(e) => setField("goals", e.target.value)}
                  placeholder="What should students be able to do by the end?"
                  maxLength={8000}
                />
              </Field>
              <Field
                label="Topic hints"
                hint="Optional — comma or newline separated. Leave blank to let the agent propose a sequence."
              >
                <textarea
                  className={TEXTAREA}
                  rows={3}
                  value={topicText}
                  onChange={(e) => setTopicText(e.target.value)}
                  placeholder="linear equations, systems, quadratics…"
                />
              </Field>
              <div className="rounded-xl bg-slate-50 p-4 text-sm text-muted">
                <p className="font-medium text-ink">What you’ll get</p>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  <li>
                    ~{form.duration_weeks * (form.sessions_per_week ?? 1)} sessions across{" "}
                    {form.duration_weeks} weeks
                  </li>
                  <li>High-level units linked to real library resources</li>
                  <li>Optional technique links when peer strategies fit</li>
                  <li>A planned class profile you can refine later</li>
                </ul>
              </div>
            </>
          )}

          <div className="flex flex-wrap items-center gap-2 pt-2">
            {step > 1 && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => setStep((s) => (s - 1) as Step)}
                disabled={generating}
              >
                Back
              </Button>
            )}
            {step < 3 ? (
              <Button
                type="button"
                disabled={!canAdvance(step) || generating}
                onClick={() => setStep((s) => (s + 1) as Step)}
              >
                Continue
              </Button>
            ) : (
              <Button
                type="button"
                loading={generating}
                disabled={!aiEnabled || generating}
                onClick={() => void runGenerate()}
              >
                Generate class plan
              </Button>
            )}
          </div>
        </form>
      </Card>

      {generating && (
        <div className="fixed inset-x-0 bottom-20 z-30 mx-auto flex w-fit items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm text-white shadow-lg md:bottom-6">
          <Spinner className="h-4 w-4" />
          Building your class from the library…
        </div>
      )}
    </div>
  );
}
