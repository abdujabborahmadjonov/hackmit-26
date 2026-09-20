import { useCallback, useEffect, useRef, useState } from "react";
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
import { useAuth } from "../auth/AuthContext";
import {
  getSearchCache,
  searchCacheKey,
  setSearchCache,
} from "../cache/searchCache";
import { TeacherCard } from "../components/TeacherCard";
import { TeacherCardSkeleton } from "../components/Skeleton";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select } from "../components/ui";

function parseRadiusKm(value: string): number | undefined {
  const radius = Number(value);
  if (!Number.isFinite(radius) || radius <= 0) return undefined;
  return radius;
}

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
  // Empty by default — a fixed 50km radius + profile coords forced a geo
  // filter on every Discover visit (and a second fetch when profile loaded).
  radius_km: "",
  minimum_rating: "",
  class_size: "",
  sort: "relevance",
};

export default function Search() {
  const { profile, loading: authLoading } = useAuth();
  const profileCoords = useRef<{ lat?: number; lon?: number }>({});
  profileCoords.current = {
    lat: profile?.latitude ?? undefined,
    lon: profile?.longitude ?? undefined,
  };
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const defaultCacheKey = searchCacheKey({
    sort: "relevance",
    limit: 24,
  });
  const cachedDefault = getSearchCache(defaultCacheKey);
  const [data, setData] = useState<TeacherSearchResponse | null>(cachedDefault);
  const [loading, setLoading] = useState(!cachedDefault);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(async (active: Filters) => {
    setError(null);
    const city = CITIES.find((c) => c.name === active.city);
    const radiusKm = parseRadiusKm(active.radius_km);
    const latitude = city?.lat ?? profileCoords.current.lat;
    const longitude = city?.lon ?? profileCoords.current.lon;
    const hasGeo = radiusKm !== undefined && latitude != null && longitude != null;
    const params = {
      query: active.query || undefined,
      subject: active.subject || undefined,
      education_level: active.education_level || undefined,
      teaching_level: active.teaching_level || undefined,
      teaching_method: active.teaching_method || undefined,
      latitude: hasGeo ? latitude : undefined,
      longitude: hasGeo ? longitude : undefined,
      radius_km: hasGeo ? radiusKm : undefined,
      minimum_rating: active.minimum_rating || undefined,
      class_size: active.class_size || undefined,
      sort: active.sort,
      limit: 24,
    };
    const key = searchCacheKey(params);
    const cached = getSearchCache(key);
    if (cached) {
      setData(cached);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await api.searchTeachers(params);
      setSearchCache(key, result);
      setData(result);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // First paint: hydrate from cache immediately, then fetch once auth is ready
  // (geo filters need profile coords only when a radius is set).
  useEffect(() => {
    if (authLoading) return;
    const handle = window.setTimeout(() => void run(filters), cachedDefault ? 0 : 250);
    return () => window.clearTimeout(handle);
    // Geographic controls apply as they change; other filters still use Submit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, filters.city, filters.radius_km, run]);

  function set<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }
  const activeFilterCount = Object.entries(filters).filter(
    ([key, value]) => value && !["query", "radius_km", "sort"].includes(key),
  ).length;

  return (
    <div>
      <PageHeader
        eyebrow="Discover educators"
        title="Find the expertise your network needs"
        description="Describe the kind of educator you want to meet in natural language, then narrow by subject, learner level, location, and classroom context."
        actions={activeFilterCount > 0 ? <Badge tone="indigo">{activeFilterCount} filters active</Badge> : undefined}
      />

      <Card className="mt-7 overflow-hidden">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run(filters);
          }}
          className="space-y-5 p-5 sm:p-6"
        >
          <div>
            <label htmlFor="educator-search" className="mb-2 block text-sm font-semibold text-ink">
              What kind of collaborator are you looking for?
            </label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <svg aria-hidden="true" className="absolute left-3.5 top-3 h-5 w-5 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="11" cy="11" r="6" />
                  <path d="m16 16 4 4" />
                </svg>
                <Input
                  id="educator-search"
                  className="py-3 pl-11 text-base"
                  value={filters.query}
                  onChange={(e) => set("query", e.target.value)}
                  placeholder="e.g. project-based physics teacher for interdisciplinary units"
                />
              </div>
              <Button type="submit" loading={loading} className="px-6">
                Search educators
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted">
              Semantic search understands meaning, so you can describe a classroom rather than guess keywords.
            </p>
          </div>

          <div className="border-t border-line pt-5">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                Refine your search
              </p>
              <button
                type="button"
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                onClick={() => {
                  setFilters(EMPTY);
                  void run(EMPTY);
                }}
              >
                Clear all
              </button>
            </div>
          <div className="grid gap-4 sm:grid-cols-3">
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
                <option value="">My location</option>
                {CITIES.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Within (km)"
              hint={
                filters.city
                  ? `Around ${filters.city}`
                  : "Around your profile location. Clear to search everywhere."
              }
            >
              <Input
                type="number"
                min={1}
                max={20000}
                value={filters.radius_km}
                onChange={(e) => set("radius_km", e.target.value)}
                placeholder="Any"
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
          </div>

          <div className="flex items-center border-t border-line pt-4">
            {data && (
              <span className="text-xs text-muted">
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
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((n) => (
            <TeacherCardSkeleton key={n} />
          ))}
        </div>
      ) : (
        <div className="stagger mt-6 grid gap-4 sm:grid-cols-2">
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
