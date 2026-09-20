/** Shared mentor list cache so Matches/Discover don't refetch on every visit. */

import type { Mentor } from "../api/types";
import { api } from "../api/client";

let allMentors: Mentor[] | null = null;
let inflight: Promise<Mentor[]> | null = null;

export function getPinnedMentors(): Promise<Mentor[]> {
  if (allMentors) {
    return Promise.resolve(allMentors.filter((mentor) => mentor.pinned));
  }
  if (!inflight) {
    inflight = api
      .mentors()
      .then((all) => {
        allMentors = all;
        return all.filter((mentor) => mentor.pinned);
      })
      .catch(() => [] as Mentor[])
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function clearMentorsCache(): void {
  allMentors = null;
  inflight = null;
}
