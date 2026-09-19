/** The controlled vocabularies the API validates against (app/taxonomy.py),
 *  plus display helpers. Keep in sync if the backend list changes. */

export const EDUCATION_LEVELS = [
  "elementary",
  "middle_school",
  "high_school",
  "university",
  "graduate",
  "adult_education",
] as const;

export const TEACHING_LEVELS = ["beginner", "intermediate", "advanced"] as const;

export const TEACHING_METHODS = [
  "project_based",
  "lecture_based",
  "collaborative",
  "socratic",
  "hands_on",
  "flipped_classroom",
  "inquiry_based",
  "game_based",
  "discussion_based",
  "problem_based",
] as const;

export const SUBJECTS = [
  "mathematics",
  "physics",
  "chemistry",
  "biology",
  "computer_science",
  "english",
  "history",
  "economics",
  "business",
  "art",
  "music",
  "engineering",
  "psychology",
  "statistics",
  "artificial_intelligence",
  "machine_learning",
] as const;

export const INSTITUTION_TYPES = [
  "public_school",
  "private_school",
  "charter_school",
  "university",
  "community_college",
  "online_academy",
  "nonprofit",
  "independent",
] as const;

/** Cities the demo data is spread across, for the geographic filter. */
export const CITIES: { name: string; lat: number; lon: number }[] = [
  { name: "Boston, Massachusetts", lat: 42.36, lon: -71.06 },
  { name: "Cambridge, Massachusetts", lat: 42.37, lon: -71.11 },
  { name: "New York, New York", lat: 40.71, lon: -74.01 },
  { name: "Toronto, Ontario", lat: 43.65, lon: -79.38 },
  { name: "Edmonton, Alberta", lat: 53.55, lon: -113.49 },
  { name: "San Francisco, California", lat: 37.77, lon: -122.42 },
  { name: "Seattle, Washington", lat: 47.61, lon: -122.33 },
  { name: "London, United Kingdom", lat: 51.51, lon: -0.13 },
  { name: "Dubai, United Arab Emirates", lat: 25.2, lon: 55.27 },
  { name: "Singapore", lat: 1.35, lon: 103.82 },
  { name: "Tashkent, Uzbekistan", lat: 41.3, lon: 69.24 },
];

const SPECIAL_CASE: Record<string, string> = {
  artificial_intelligence: "Artificial Intelligence",
  esl: "ESL",
  stem_outreach: "STEM Outreach",
  cad_basics: "CAD Basics",
};

/** "high_school" -> "High School" */
export function humanize(value?: string | null): string {
  if (!value) return "";
  if (SPECIAL_CASE[value]) return SPECIAL_CASE[value];
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** The six components of a match score, in weight order, with a colour each. */
export const FACTOR_META: Record<string, { label: string; colour: string }> = {
  semantic: { label: "Teaching philosophy", colour: "bg-indigo-500" },
  expertise: { label: "Subjects & expertise", colour: "bg-emerald-500" },
  education: { label: "Education level", colour: "bg-amber-500" },
  teaching_level: { label: "Learner level", colour: "bg-sky-500" },
  location: { label: "Proximity", colour: "bg-rose-500" },
  class_size: { label: "Class size", colour: "bg-violet-500" },
};
