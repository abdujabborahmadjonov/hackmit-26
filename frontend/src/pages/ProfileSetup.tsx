import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
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
import { Button, Card, ErrorNote, Field, Input, Select } from "../components/ui";

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
  const { profile, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<ProfileInput>(EMPTY);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

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

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">
        {isNew ? "Tell us how you teach" : "Your teaching profile"}
      </h1>
      <p className="mt-2 text-sm text-muted">
        Your teaching style and bio are turned into a semantic vector — that's 30% of every match
        score. The structured fields below carry the other 70%.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-5">
        <Card className="space-y-4 p-5">
          <Field
            label="How do you teach?"
            hint="The single most important field. Write it as you'd describe your classroom to a colleague."
          >
            <textarea
              className="w-full rounded-lg bg-white px-3 py-2 text-sm text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={3}
              value={form.teaching_style ?? ""}
              onChange={(e) => set("teaching_style", e.target.value)}
              placeholder="Project-based and collaborative. Students ship a working app each unit, with peer code review built in."
            />
          </Field>
          <Field label="Short bio">
            <textarea
              className="w-full rounded-lg bg-white px-3 py-2 text-sm text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={2}
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

        <Card className="space-y-4 p-5">
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

        <Card className="grid gap-4 p-5 sm:grid-cols-2">
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
        </Card>

        <ErrorNote error={error} />
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy}>
            {isNew ? "Save and see my matches" : "Save changes"}
          </Button>
          {saved && <span className="text-sm text-emerald-600">Saved — matches updated.</span>}
          {profile?.has_embedding && (
            <span className="ml-auto text-xs text-muted">Semantic vector: ready</span>
          )}
        </div>
      </form>
    </div>
  );
}
