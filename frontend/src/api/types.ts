/** Mirrors the FastAPI response models. Kept hand-written and small on purpose:
 *  the shapes we actually render, not the whole OpenAPI surface. */

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserPublic {
  id: string;
  first_name: string;
  last_name: string;
  profile_photo_url: string | null;
  is_verified: boolean;
  created_at?: string | null;
}

export interface UserPrivate extends UserPublic {
  email: string;
}

export interface ProfileInput {
  bio?: string | null;
  location_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  education_levels: string[];
  subjects: string[];
  fields_of_expertise: string[];
  teaching_levels: string[];
  teaching_methods: string[];
  teaching_style?: string | null;
  class_size?: number | null;
  years_experience?: number | null;
  languages: string[];
  institution?: string | null;
  institution_type?: string | null;
}

export interface Profile extends ProfileInput {
  id: string;
  user_id: string;
  user?: UserPublic | null;
  average_rating: number;
  rating_count: number;
  has_embedding: boolean;
}

export interface TeacherSummary {
  user_id: string;
  first_name: string;
  last_name: string;
  profile_photo_url: string | null;
  bio: string | null;
  location_name: string | null;
  education_levels: string[];
  subjects: string[];
  fields_of_expertise: string[];
  teaching_levels: string[];
  teaching_methods: string[];
  teaching_style: string | null;
  class_size: number | null;
  years_experience: number | null;
  languages: string[];
  institution: string | null;
  institution_type: string | null;
  average_rating: number;
  rating_count: number;
  distance_km: number | null;
}

/** One weighted factor behind a match - what powers "Why this match?". */
export interface MatchReason {
  factor: string;
  label: string;
  score: number;
  weight: number;
  contribution: number;
}

export interface Recommendation {
  teacher: TeacherSummary;
  match_score: number;
  /** All six factor scores, 0-1. Complete, unlike `explanation` — so the
   *  client can re-rank under different weights without another request. */
  components: Record<string, number>;
  reasons: string[];
  explanation: MatchReason[];
  distance_km: number | null;
}

export interface RecommendationResponse {
  items: Recommendation[];
  generated_for: string;
  candidate_pool_size: number;
  took_ms: number;
  weights: Record<string, number>;
}

export interface TeacherSearchResult {
  teacher: TeacherSummary;
  score: number;
  distance_km: number | null;
}

export interface TeacherSearchResponse {
  items: TeacherSearchResult[];
  total: number;
  limit: number;
  offset: number;
  engine: string;
  took_ms: number;
}

export interface Resource {
  id: string;
  owner_id: string;
  owner?: UserPublic | null;
  title: string;
  description: string | null;
  resource_type: string | null;
  subject: string | null;
  education_level: string | null;
  difficulty: string | null;
  teaching_method: string | null;
  tags: string[];
  file_url: string | null;
  file_name: string | null;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  download_count: number;
  created_at?: string | null;
}

export interface ResourceSearchResponse {
  items: { resource: Resource; score: number }[];
  total: number;
  limit: number;
  offset: number;
  engine: string;
  took_ms: number;
}

export interface RecommendedResource {
  resource: Resource;
  match_score: number;
  reasons: string[];
}

export type ConnectionStatus = "pending" | "accepted" | "rejected" | "blocked";

export interface Connection {
  id: string;
  requester_id: string;
  receiver_id: string;
  status: ConnectionStatus;
  requester?: UserPublic | null;
  receiver?: UserPublic | null;
  updated_at?: string | null;
}

export interface Rating {
  id: string;
  reviewer_id: string;
  teacher_id: string;
  reviewer?: UserPublic | null;
  rating: number;
  comment: string | null;
  is_verified_student: boolean;
  created_at?: string | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  content: string;
  created_at: string;
  read_at: string | null;
}

export interface Conversation {
  id: string;
  participants: UserPublic[];
  last_message: Message | null;
  unread_count: number;
  updated_at?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}


/** A profile suggested from an uploaded document. Nothing is saved until the
 *  teacher reviews it and submits the form. */
export interface ProfileDraft {
  subjects: string[];
  education_levels: string[];
  teaching_levels: string[];
  teaching_methods: string[];
  fields_of_expertise: string[];
  teaching_style: string;
  class_size: number | null;
  confidence: string;
  source_name: string | null;
}


/** One thing a guide is allowed to draw on. Shown as a footnote under a reply. */
export interface MentorSource {
  id: string;
  label: string;
  url: string;
  kind: "interview" | "talk" | "book" | "course" | "article" | "other";
}

export interface MentorVoice {
  enabled: boolean;
  provider: "browser" | "none";
  prefer: string[];
  pitch: number;
  rate: number;
  /** Names a real person this voice imitates. Requires likeness consent, so
   *  it is null on every persona until someone records that permission. */
  clone_of: string | null;
}

export interface MentorAvatar {
  enabled: boolean;
  /** "stylised" is an abstract form; "likeness" needs the person's consent. */
  kind: "stylised" | "likeness";
  model_url: string;
  accent: string;
}

/** An educator you can hold a live conversation with. The persona is data on
 *  the server - `available` is false when that deployment has no model key.
 *
 *  `mode` is the difference that matters: a `first_person` persona speaks as
 *  the educator (only ever a composite, or someone who agreed to it), while a
 *  `guide` speaks *about* a real educator's published teaching and cites it. */
export interface Mentor {
  slug: string;
  name: string;
  title: string;
  institution: string;
  mode: "first_person" | "guide";
  pinned: boolean;
  location_name: string;
  known_for: string;
  tagline: string;
  avatar_seed: string;
  avatar_url: string;
  /** Absent when the API predates voice mode - always guard. */
  voice?: MentorVoice;
  avatar?: MentorAvatar;
  /** Whether this persona may look things up mid-conversation. */
  research?: boolean;
  synthetic: boolean;
  disclaimer: string;
  subjects: string[];
  years_experience: number | null;
  opening_line: string;
  suggested_questions: string[];
  collaborates_on: string[];
  sources: MentorSource[];
  /** False for a guide whose sources have not been filled in yet. */
  has_material: boolean;
  available: boolean;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}
