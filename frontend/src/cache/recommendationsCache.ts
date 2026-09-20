/** In-memory Matches page cache — survives React Router unmounts.

Navigate away and back without re-hitting `/recommendations` (and without
flashing skeletons) unless the user forces a refresh or saves weight prefs.
Stale entries still paint instantly; a background revalidate refreshes them.
*/

import type { RecommendationResponse } from "../api/types";
import type { Weights } from "../components/WeightStudio";

export interface RecommendationsCacheEntry {
  data: RecommendationResponse;
  weights: Weights;
  weightsSaved: boolean;
  dismissed: string[];
  connected: string[];
  aiEnabled: boolean;
  fetchedAt: number;
}

/** Show instantly, revalidate in the background after this age. */
export const RECOMMENDATIONS_STALE_MS = 90_000;

let entry: RecommendationsCacheEntry | null = null;
let inflight: Promise<RecommendationResponse> | null = null;

export function getRecommendationsCache(): RecommendationsCacheEntry | null {
  return entry;
}

export function recommendationsCacheIsStale(
  current: RecommendationsCacheEntry | null = entry,
  maxAgeMs = RECOMMENDATIONS_STALE_MS,
): boolean {
  if (!current) return true;
  return Date.now() - current.fetchedAt > maxAgeMs;
}

export function setRecommendationsCache(next: RecommendationsCacheEntry): void {
  entry = next;
}

export function patchRecommendationsCache(
  patch: Partial<Omit<RecommendationsCacheEntry, "fetchedAt">> & {
    fetchedAt?: number;
  },
): void {
  if (!entry) return;
  entry = { ...entry, ...patch };
}

export function clearRecommendationsCache(): void {
  entry = null;
  inflight = null;
}

/** Share one in-flight Matches request across StrictMode double-mounts. */
export function loadRecommendationsShared(
  fetcher: () => Promise<RecommendationResponse>,
): Promise<RecommendationResponse> {
  if (inflight) return inflight;
  inflight = fetcher().finally(() => {
    inflight = null;
  });
  return inflight;
}
