import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { TeacherSearchResponse } from "../api/types";
import {
  CITIES,
  EDUCATION_LEVELS,
  SUBJECTS,
  TEACHING_LEVELS,
  TEACHING_METHODS,
  humanize,
} from "../api/vocab";
import { TeacherCard } from "../components/TeacherCard";
import { TeacherCardSkeleton } from "../components/Skeleton";
import { Button, Card, ErrorNote, Field, Input, Select } from "../components/ui";

interface Filters {
  query: string;
  subject: string;
  education_level: string;
  teaching_level: string;
  teaching_method: string;
  city: string;
  radius_km: string;
  minimum_rating: string;
  class_size: string;
  sort: string;
}

const EMPTY: Filters = {
  query: "",
  subject: "",
  education_level: "",
  teaching_level: "",
  teaching_method: "",
  city: "",
  radius_km: "50",
  minimum_rating: "",
  class_size: "",
  sort: "relevance",
};

export default function Search() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [data, setData] = useState<TeacherSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(async (active: Filters) => {
    setLoading(true);
    setError(null);
    const city = CITIES.find((c) => c.name === active.city);
    try {
      setData(
        await api.searchTeachers({
          query: active.query || undefined,
          subject: active.subject || undefined,
          education_level: active.education_level || undefined,
          teaching_level: active.teaching_level || undefined,
          teaching_method: active.teaching_method || undefined,
          latitude: city?.lat,
          longitude: city?.lon,
          radius_km: city ? Number(active.radius_km) : undefined,
          minimum_rating: active.minimum_rating || undefined,
          class_size: active.class_size || undefined,
          sort: active.sort,
          limit: 24,
        }),
      );
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run(EMPTY);
  }, [run]);

  function set<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Search educators</h1>
      <p className="mt-1 text-sm text-muted">
        Filters run in Postgres; the free-text box additionally searches meaning, not just words.
      </p>

      <Card className="mt-5 p-5">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(filters);
          }}
          className="space-y-4"
        >
          <Field label="What are you looking for?">
            <Input
              value={filters.query}
              onChange={(e) => set("query", e.target.value)}
              placeholder="students build real software in teams"
            />
          </Field>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Subject">
              <Select value={filters.subject} onChange={(e) => set("subject", e.target.value)}>
                <option value="">Any</option>
                {SUBJECTS.map((s) => (
                  <option key={s} value={s}>
                    {humanize(s)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Education level">
              <Select
                value={filters.education_level}
                onChange={(e) => set("education_level", e.target.value)}
              >
                <option value="">Any</option>
                {EDUCATION_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {humanize(l)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Teaching method">
              <Select
                value={filters.teaching_method}
                onChange={(e) => set("teaching_method", e.target.value)}
              >
                <option value="">Any</option>
                {TEACHING_METHODS.map((m) => (
                  <option key={m} value={m}>
                    {humanize(m)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Near">
              <Select value={filters.city} onChange={(e) => set("city", e.target.value)}>
                <option value="">Anywhere</option>
                {CITIES.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Within (km)">
              <Input
                type="number"
                min={1}
                max={20000}
                value={filters.radius_km}
                onChange={(e) => set("radius_km", e.target.value)}
                disabled={!filters.city}
              />
            </Field>
            <Field label="Learner level">
              <Select
                value={filters.teaching_level}
                onChange={(e) => set("teaching_level", e.target.value)}
              >
                <option value="">Any</option>
                {TEACHING_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {humanize(l)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Minimum rating">
              <Select
                value={filters.minimum_rating}
                onChange={(e) => set("minimum_rating", e.target.value)}
              >
                <option value="">Any</option>
                <option value="3">3★ and up</option>
                <option value="4">4★ and up</option>
                <option value="4.5">4.5★ and up</option>
              </Select>
            </Field>
            <Field label="Class size near">
              <Input
                type="number"
                min={1}
                value={filters.class_size}
                onChange={(e) => set("class_size", e.target.value)}
                placeholder="e.g. 25"
              />
            </Field>
            <Field label="Sort by">
              <Select value={filters.sort} onChange={(e) => set("sort", e.target.value)}>
                <option value="relevance">Relevance</option>
                <option value="rating">Rating</option>
                <option value="experience">Experience</option>
                <option value="distance">Distance</option>
                <option value="newest">Newest</option>
              </Select>
            </Field>
          </div>

          <div className="flex items-center gap-3">
            <Button type="submit" loading={loading}>
              Search
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setFilters(EMPTY);
                void run(EMPTY);
              }}
            >
              Reset
            </Button>
            {data && (
              <span className="ml-auto text-xs text-muted">
                {data.total.toLocaleString()} educators · {Math.round(data.took_ms)} ms ·{" "}
                {data.engine}
              </span>
            )}
          </div>
        </form>
      </Card>

      <div className="mt-4">
        <ErrorNote error={error} />
      </div>

      {loading ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((n) => (
            <TeacherCardSkeleton key={n} />
          ))}
        </div>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {data?.items.map((hit) => (
            <TeacherCard key={hit.teacher.user_id} teacher={hit.teacher} score={hit.score} />
          ))}
        </div>
      )}
      {data && data.items.length === 0 && !loading && (
        <Card className="mt-4 p-10 text-center text-sm text-muted">
          No educators match those filters. Try widening the radius or clearing a filter.
        </Card>
      )}
    </div>
  );
}
