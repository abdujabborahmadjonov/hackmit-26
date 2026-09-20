import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ProfileInput } from "../api/types";
import {
  CITIES,
  EDUCATION_LEVELS,
  INSTITUTION_TYPES,
  SUBJECTS,
  TEACHING_LEVELS,
  TEACHING_METHODS,
  humanize,
} from "../api/vocab";
import { useAuth } from "../auth/AuthContext";
import { ChipSelect, TagInput } from "../components/ChipSelect";
import { SyllabusImport } from "../components/SyllabusImport";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select } from "../components/ui";

const EMPTY: ProfileInput = {
  bio: "",
  location_name: "",
  latitude: null,
  longitude: null,
  education_levels: [],
  subjects: [],
  fields_of_expertise: [],
  teaching_levels: [],
  teaching_methods: [],
  teaching_style: "",
  class_size: null,
  years_experience: null,
  languages: ["English"],
  institution: "",
  institution_type: null,
};

export default function ProfileSetup() {
  const { user, profile, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<ProfileInput>(EMPTY);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);

  useEffect(() => {
    void api
      .aiStatus()
      .then((status) => setAiEnabled(status.enabled))
      .catch(() => setAiEnabled(false));
  }, []);

  useEffect(() => {
    if (profile) {
      setForm({ ...EMPTY, ...profile });
    }
  }, [profile]);

  function set<K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (profile) await api.updateProfile(form);
      else await api.createProfile(form);
      await refreshProfile();
      setSaved(true);
      if (!profile) navigate("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const isNew = !profile;
  const completionFields = [
    form.teaching_style,
    form.bio,
    form.education_levels.length,
    form.subjects.length,
    form.teaching_methods.length,
    form.location_name,
    form.institution,
    form.fields_of_expertise.length,
  ];
  const completion = Math.round(
    (completionFields.filter((value) => Boolean(value)).length / completionFields.length) * 100,
  );

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        eyebrow={isNew ? "Profile setup" : "Profile settings"}
        title={isNew ? "Tell us how you teach" : "Your teaching profile"}
        description="The strongest matches start with an honest picture of your classroom—your methods, learners, expertise, and the environment where you do your best work."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {profile?.has_embedding ? <Badge tone="emerald">Semantic profile ready</Badge> : null}
            {user && profile ? (
              <Link
                to={`/teachers/${user.id}`}
                className="press inline-flex items-center rounded-xl bg-white px-3 py-1.5 text-sm font-semibold text-ink ring-1 ring-line hover:bg-slate-50"
              >
                View my page
              </Link>
            ) : null}
          </div>
        }
      />

      <div className="mt-8 rounded-2xl bg-indigo-50 p-5 ring-1 ring-indigo-100">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-indigo-950">Profile strength</p>
            <p className="mt-0.5 text-xs text-indigo-700">
              Richer profiles produce more useful recommendations.
            </p>
          </div>
          <span className="text-2xl font-semibold tabular-nums text-indigo-700">{completion}%</span>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
          <div
            className="h-full rounded-full bg-indigo-600 transition-all"
            style={{ width: `${completion}%` }}
          />
        </div>
      </div>

      {aiEnabled && (
        <div className="mt-6">
          <SyllabusImport
            onExtract={(draft) =>
              setForm((current) => ({
                ...current,
                // Merge, never clobber: anything already typed wins.
                subjects: current.subjects.length ? current.subjects : draft.subjects,
                education_levels: current.education_levels.length
                  ? current.education_levels
                  : draft.education_levels,
                teaching_levels: current.teaching_levels.length
                  ? current.teaching_levels
                  : draft.teaching_levels,
                teaching_methods: current.teaching_methods.length
                  ? current.teaching_methods
                  : draft.teaching_methods,
                fields_of_expertise: current.fields_of_expertise.length
                  ? current.fields_of_expertise
                  : draft.fields_of_expertise,
                teaching_style: current.teaching_style || draft.teaching_style,
                class_size: current.class_size ?? draft.class_size,
              }))
            }
          />
        </div>
      )}

      <form onSubmit={submit} className="mt-6 space-y-6">
        <Card className="space-y-5 p-6 sm:p-7">
          <div className="border-b border-line pb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">
              01 · Teaching identity
            </p>
            <h2 className="mt-1 text-lg font-semibold text-ink">What is your classroom like?</h2>
            <p className="mt-1 text-sm text-muted">
              These words drive the semantic portion of every recommendation.
            </p>
          </div>
          <Field
            label="How do you teach?"
            hint="The single most important field. Write it as you'd describe your classroom to a colleague."
          >
            <textarea
              className="w-full rounded-xl bg-white px-3.5 py-3 text-sm leading-6 text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={5}
              value={form.teaching_style ?? ""}
              onChange={(e) => set("teaching_style", e.target.value)}
              placeholder="Project-based and collaborative. Students ship a working app each unit, with peer code review built in."
            />
          </Field>
          <Field label="Short bio">
            <textarea
              className="w-full rounded-xl bg-white px-3.5 py-3 text-sm leading-6 text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={3}
              value={form.bio ?? ""}
              onChange={(e) => set("bio", e.target.value)}
              placeholder="I teach computer science using project-based learning."
            />
          </Field>
          <Field label="Teaching methods">
            <ChipSelect
              options={TEACHING_METHODS}
              value={form.teaching_methods}
              onChange={(next) => set("teaching_methods", next)}
              max={4}
            />
          </Field>
        </Card>

        <Card className="space-y-5 p-6 sm:p-7">
          <div className="border-b border-line pb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">
              02 · Subjects and learners
            </p>
            <h2 className="mt-1 text-lg font-semibold text-ink">Where can you contribute most?</h2>
            <p className="mt-1 text-sm text-muted">
              Choose the areas you teach today and the expertise you would share with a colleague.
            </p>
          </div>
          <Field label="Education levels you teach">
            <ChipSelect
              options={EDUCATION_LEVELS}
              value={form.education_levels}
              onChange={(next) => set("education_levels", next)}
            />
          </Field>
          <Field label="Learner levels">
            <ChipSelect
              options={TEACHING_LEVELS}
              value={form.teaching_levels}
              onChange={(next) => set("teaching_levels", next)}
            />
          </Field>
          <Field label="Subjects">
            <ChipSelect
              options={SUBJECTS}
              value={form.subjects.filter((s) => (SUBJECTS as readonly string[]).includes(s))}
              onChange={(next) => {
                const custom = form.subjects.filter(
                  (s) => !(SUBJECTS as readonly string[]).includes(s),
                );
                set("subjects", [...next, ...custom]);
              }}
            />
          </Field>
          <Field label="Other subjects or specialities" hint="Comma separated, e.g. python, robotics">
            <TagInput
              value={form.subjects.filter((s) => !(SUBJECTS as readonly string[]).includes(s))}
              onChange={(custom) => {
                const known = form.subjects.filter((s) =>
                  (SUBJECTS as readonly string[]).includes(s),
                );
                set("subjects", [...known, ...custom]);
              }}
              placeholder="python, robotics"
            />
          </Field>
          <Field label="Fields of expertise" hint="What you'd run a workshop on.">
            <TagInput
              value={form.fields_of_expertise}
              onChange={(next) => set("fields_of_expertise", next)}
              placeholder="software_engineering, curriculum_design"
            />
          </Field>
        </Card>

        <Card className="p-6 sm:p-7">
          <div className="mb-5 border-b border-line pb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">
              03 · Teaching context
            </p>
            <h2 className="mt-1 text-lg font-semibold text-ink">Ground your profile in the real world</h2>
            <p className="mt-1 text-sm text-muted">
              We only use city-level location—never a street address.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
          <Field label="City" hint="City level only — never a street address.">
            <Select
              value={form.location_name ?? ""}
              onChange={(e) => {
                const city = CITIES.find((c) => c.name === e.target.value);
                set("location_name", e.target.value);
                set("latitude", city?.lat ?? null);
                set("longitude", city?.lon ?? null);
              }}
            >
              <option value="">Select a city…</option>
              {CITIES.map((city) => (
                <option key={city.name} value={city.name}>
                  {city.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Institution">
            <Input
              value={form.institution ?? ""}
              onChange={(e) => set("institution", e.target.value)}
              placeholder="Boston Latin School"
            />
          </Field>
          <Field label="Institution type">
            <Select
              value={form.institution_type ?? ""}
              onChange={(e) => set("institution_type", e.target.value || null)}
            >
              <option value="">—</option>
              {INSTITUTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanize(type)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Typical class size">
            <Input
              type="number"
              min={1}
              max={1000}
              value={form.class_size ?? ""}
              onChange={(e) => set("class_size", e.target.value ? Number(e.target.value) : null)}
            />
          </Field>
          <Field label="Years teaching">
            <Input
              type="number"
              min={0}
              max={70}
              value={form.years_experience ?? ""}
              onChange={(e) =>
                set("years_experience", e.target.value ? Number(e.target.value) : null)
              }
            />
          </Field>
          <Field label="Languages" hint="Comma separated.">
            <TagInput value={form.languages} onChange={(next) => set("languages", next)} />
          </Field>
          </div>
        </Card>

        <ErrorNote error={error} />
        <div className="sticky bottom-20 z-10 flex flex-wrap items-center gap-3 rounded-2xl bg-white/95 p-4 ring-1 ring-line shadow-lg backdrop-blur md:bottom-4">
          <Button type="submit" loading={busy}>
            {isNew ? "Save and see my matches" : "Save changes"}
          </Button>
          {saved && <span className="text-sm text-emerald-600">Saved — matches updated.</span>}
          <span className="ml-auto text-xs text-muted">Profile strength: {completion}%</span>
        </div>
      </form>
    </div>
  );
}
