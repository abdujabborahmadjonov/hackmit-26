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
