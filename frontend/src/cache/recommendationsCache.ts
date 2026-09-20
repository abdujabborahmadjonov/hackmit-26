/** In-memory Matches page cache — survives React Router unmounts.

Navigate away and back without re-hitting `/recommendations` (and without
flashing skeletons) unless the user forces a refresh or saves weight prefs.
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

let entry: RecommendationsCacheEntry | null = null;

export function getRecommendationsCache(): RecommendationsCacheEntry | null {
  return entry;
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
}
