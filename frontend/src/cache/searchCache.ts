/** In-memory Discover search cache — avoids refetching the default browse. */

import type { TeacherSearchResponse } from "../api/types";

type CacheKey = string;

const store = new Map<CacheKey, { data: TeacherSearchResponse; fetchedAt: number }>();
const TTL_MS = 60_000;

export function searchCacheKey(params: Record<string, unknown>): CacheKey {
  return JSON.stringify(params, Object.keys(params).sort());
}

export function getSearchCache(key: CacheKey): TeacherSearchResponse | null {
  const hit = store.get(key);
  if (!hit) return null;
  if (Date.now() - hit.fetchedAt > TTL_MS) {
    store.delete(key);
    return null;
  }
  return hit.data;
}

export function setSearchCache(key: CacheKey, data: TeacherSearchResponse): void {
  store.set(key, { data, fetchedAt: Date.now() });
  // Bound memory: keep the most recent handful of queries.
  if (store.size > 12) {
    const oldest = store.keys().next().value;
    if (oldest !== undefined) store.delete(oldest);
  }
}

export function clearSearchCache(): void {
  store.clear();
}
