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
  knowledge_of_material: number | null;
  presentation: number | null;
  friendliness: number | null;
  other: number | null;
  comment: string | null;
  is_verified_student: boolean;
  created_at?: string | null;
}

export interface AspectAverages {
  knowledge_of_material: number | null;
  presentation: number | null;
  friendliness: number | null;
  other: number | null;
}

export interface RatingSummary {
  teacher_id: string;
  average_rating: number;
  rating_count: number;
  verified_student_count: number;
  distribution: Record<string, number>;
  aspect_averages: AspectAverages;
}

export interface StudentToken {
  id: string;
  teacher_id: string;
  label: string | null;
  expires_at: string;
  max_uses: number | null;
  use_count: number;
  is_revoked: boolean;
  is_active: boolean;
  created_at?: string | null;
  /** Only present immediately after creation. */
  token?: string;
}

export interface StudentRatingInput {
  verification_token: string;
  knowledge_of_material: number;
  presentation: number;
  friendliness: number;
  other: number;
  comment?: string;
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

export type ForumCategory =
  | "general"
  | "collaboration"
  | "curriculum"
  | "classroom"
  | "resources"
  | "technology";

export interface ForumTopic {
  id: string;
  author_id: string;
  author: UserPublic | null;
  title: string;
  body: string;
  category: ForumCategory | string;
  reply_count: number;
  last_activity_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ForumPost {
  id: string;
  topic_id: string;
  author_id: string;
  author: UserPublic | null;
  content: string;
  created_at?: string | null;
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
