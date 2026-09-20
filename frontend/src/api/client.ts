/** Thin typed wrapper over fetch. One place that knows about the token,
 *  the base URL, and how the API reports errors. */

import type {
  ClassProfile,
  ClassProfileDraft,
  ClassProfileInput,
  Connection,
  ProfileDraft,
  Conversation,
  ForumPost,
  ForumTopic,
  Message,
  Page,
  PlanningResponse,
  Profile,
  ProfileInput,
  Rating,
  RatingLink,
  RatingSummary,
  RecommendationResponse,
  RecommendedResource,
  Resource,
  ResourceSearchResponse,
  StudentRatingInput,
  StudentToken,
  TeacherSearchResponse,
  Technique,
  TechniqueDraft,
  TechniqueRatingCreate,
  TechniqueSearchParseResponse,
  TechniqueSearchRunResponse,
  TokenResponse,
  UserPrivate,
} from "./types";

export const API_URL: string =
  import.meta.env.VITE_API_URL ?? "https://edumatch-api-asbp.onrender.com";

const TOKEN_KEY = "edumatch.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing - the session just won't persist */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

interface FieldError {
  field: string;
  message: string;
}

/** FastAPI reports errors three different ways; flatten them into one string. */
function readError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object") {
    const payload = body as { detail?: unknown; errors?: FieldError[] };
    if (Array.isArray(payload.errors) && payload.errors.length) {
      return new ApiError(
        status,
        payload.errors.map((e) => `${e.field}: ${e.message}`).join("; "),
      );
    }
    if (typeof payload.detail === "string") return new ApiError(status, payload.detail);
    if (Array.isArray(payload.detail)) {
      const parts = (payload.detail as { loc?: unknown[]; msg?: string }[]).map((d) =>
        [Array.isArray(d.loc) ? d.loc.slice(1).join(".") : "", d.msg].filter(Boolean).join(": "),
      );
      return new ApiError(status, parts.join("; "));
    }
  }
  return new ApiError(status, `Request failed (${status})`);
}

type Query = Record<string, string | number | boolean | undefined | null | string[]>;

function toQueryString(params?: Query): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.append(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(
  path: string,
  options: RequestInit & { query?: Query } = {},
): Promise<T> {
  const { query, headers, ...init } = options;
  const token = getToken();
  const response = await fetch(`${API_URL}${path}${toQueryString(query)}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    if (response.status === 401 && token) setToken(null);
    throw readError(response.status, body);
  }
  return body as T;
}

export const api = {
  // --- auth ---
  register: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }) => request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(data) }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<UserPrivate>("/auth/me"),

  // --- profiles ---
  myProfile: () => request<Profile>("/profiles/me"),
  profile: (userId: string) => request<Profile>(`/profiles/${userId}`),
  createProfile: (data: ProfileInput) =>
    request<Profile>("/profiles", { method: "POST", body: JSON.stringify(data) }),
  updateProfile: (data: Partial<ProfileInput>) =>
    request<Profile>("/profiles/me", { method: "PUT", body: JSON.stringify(data) }),

  // --- the main event ---
  recommendations: (params?: { limit?: number; exclude_connected?: boolean }) =>
    request<RecommendationResponse>("/recommendations", { query: params }),

  explain: (userId: string) =>
    request<RecommendationResponse["items"][number]>(`/recommendations/${userId}/explain`),

  feedback: (userId: string, feedback: "saved" | "dismissed" | "connected") =>
    request<{ detail: string }>(`/recommendations/${userId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),

  // --- search ---
  searchTeachers: (params: Query) =>
    request<TeacherSearchResponse>("/search/teachers", { query: params }),

  searchEngine: () =>
    request<{ provider: string; reachable?: boolean }>("/search/engine"),

  // --- resources ---
  resources: (params?: Query) => request<ResourceSearchResponse>("/resources", { query: params }),
  recommendedResources: (limit = 8) =>
    request<RecommendedResource[]>("/resources/recommended", { query: { limit } }),
  createResource: (data: Partial<Resource>) =>
    request<Resource>("/resources", { method: "POST", body: JSON.stringify(data) }),
  uploadResource: (form: FormData) =>
    request<Resource>("/resources/upload", { method: "POST", body: form }),
  deleteResource: (id: string) =>
    request<{ detail: string }>(`/resources/${id}`, { method: "DELETE" }),

  // --- ratings ---
  ratings: (teacherId: string) => request<Page<Rating>>(`/teachers/${teacherId}/ratings`),
  ratingSummary: (teacherId: string) =>
    request<RatingSummary>(`/teachers/${teacherId}/ratings/summary`),
  rate: (teacherId: string, rating: number, comment?: string) =>
    request<Rating>(`/teachers/${teacherId}/ratings`, {
      method: "POST",
      body: JSON.stringify({ rating, comment: comment || null }),
    }),
  rateAsStudent: (teacherId: string, data: StudentRatingInput) =>
    request<Rating>(`/teachers/${teacherId}/ratings`, {
      method: "POST",
      body: JSON.stringify({
        verification_token: data.verification_token,
        knowledge_of_material: data.knowledge_of_material,
        presentation: data.presentation,
        friendliness: data.friendliness,
        other: data.other,
        comment: data.comment || null,
      }),
    }),

  // --- student verification tokens ---
  studentTokens: () => request<Page<StudentToken>>("/teachers/me/student-tokens"),
  createStudentToken: (data: {
    duration_minutes: number;
    label?: string;
    max_uses?: number | null;
  }) =>
    request<StudentToken>("/teachers/me/student-tokens", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  revokeStudentToken: (tokenId: string) =>
    request<{ detail: string }>(`/teachers/me/student-tokens/${tokenId}`, {
      method: "DELETE",
    }),

  // --- connections ---
  connections: (params?: Query) => request<Page<Connection>>("/connections", { query: params }),
  connect: (receiverId: string) =>
    request<Connection>("/connections", {
      method: "POST",
      body: JSON.stringify({ receiver_id: receiverId }),
    }),
  respondToConnection: (id: string, status: "accepted" | "rejected" | "blocked") =>
    request<Connection>(`/connections/${id}`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    }),

  // --- messages ---
  conversations: () => request<Page<Conversation>>("/messages/conversations"),
  startConversation: (participantId: string, content?: string) =>
    request<Conversation>("/messages/conversations", {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId, content: content || null }),
    }),
  messages: (conversationId: string) =>
    request<Page<Message>>(`/messages/conversations/${conversationId}/messages`),
  sendMessage: (conversationId: string, content: string) =>
    request<Message>(`/messages/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  markRead: (conversationId: string) =>
    request<{ detail: string }>(`/messages/conversations/${conversationId}/read`, {
      method: "POST",
    }),

  // --- forum ---
  forumTopics: (params?: Query) =>
    request<Page<ForumTopic>>("/forum/topics", { query: params }),
  forumTopic: (topicId: string) => request<ForumTopic>(`/forum/topics/${topicId}`),
  createForumTopic: (data: { title: string; body: string; category?: string }) =>
    request<ForumTopic>("/forum/topics", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateForumTopic: (
    topicId: string,
    data: { title?: string; body?: string; category?: string },
  ) =>
    request<ForumTopic>(`/forum/topics/${topicId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteForumTopic: (topicId: string) =>
    request<{ detail: string }>(`/forum/topics/${topicId}`, { method: "DELETE" }),
  forumPosts: (topicId: string, params?: Query) =>
    request<Page<ForumPost>>(`/forum/topics/${topicId}/posts`, { query: params }),
  createForumPost: (topicId: string, content: string) =>
    request<ForumPost>(`/forum/topics/${topicId}/posts`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  updateForumPost: (postId: string, content: string) =>
    request<ForumPost>(`/forum/posts/${postId}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  deleteForumPost: (postId: string) =>
    request<{ detail: string }>(`/forum/posts/${postId}`, { method: "DELETE" }),

  // --- generative features (503 when the deployment has no key) ---
  aiStatus: () => request<{ enabled: boolean; features: string[] }>("/ai/status"),

  collaborationBrief: (teacherId: string) =>
    request<{ brief: string; teacher_id: string; cached: boolean }>(`/ai/brief/${teacherId}`),

  profileFromDocument: (input: File | string) => {
    const form = new FormData();
    if (typeof input === "string") form.append("text", input);
    else form.append("file", input);
    return request<ProfileDraft>("/ai/profile-from-document", { method: "POST", body: form });
  },

  // --- class profiles ---
  classProfiles: (params?: Query) =>
    request<Page<ClassProfile>>("/class-profiles", { query: params }),
  classProfile: (id: string) => request<ClassProfile>(`/class-profiles/${id}`),
  createClassProfile: (data: ClassProfileInput) =>
    request<ClassProfile>("/class-profiles", { method: "POST", body: JSON.stringify(data) }),
  updateClassProfile: (id: string, data: Partial<ClassProfileInput>) =>
    request<ClassProfile>(`/class-profiles/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  promoteClassProfile: (
    id: string,
    data: { class_size: number; format?: string; notes?: string | null },
  ) =>
    request<ClassProfile>(`/class-profiles/${id}/promote`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteClassProfile: (id: string) =>
    request<{ detail: string }>(`/class-profiles/${id}`, { method: "DELETE" }),
  classFromDocument: (input: File | string) => {
    const form = new FormData();
    if (typeof input === "string") form.append("text", input);
    else form.append("file", input);
    return request<ClassProfileDraft>("/class-profiles/from-document", {
      method: "POST",
      body: form,
    });
  },

  // --- techniques ---
  techniques: (params?: { mine?: boolean; limit?: number; offset?: number }) =>
    request<Page<Technique>>("/techniques", { query: params }),
  technique: (id: string) => request<Technique>(`/techniques/${id}`),
  createTechnique: (data: Partial<Technique> & {
    title: string;
    summary: string;
    steps: string;
    concept_ids?: string[];
    problem_types?: string[];
  }) => request<Technique>("/techniques", { method: "POST", body: JSON.stringify(data) }),
  updateTechnique: (id: string, data: Partial<Technique> & { concept_ids?: string[] }) =>
    request<Technique>(`/techniques/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTechnique: (id: string) =>
    request<{ detail: string }>(`/techniques/${id}`, { method: "DELETE" }),
  techniqueFromDocument: (input: File | string) => {
    const form = new FormData();
    if (typeof input === "string") form.append("text", input);
    else form.append("file", input);
    return request<TechniqueDraft>("/techniques/from-document", { method: "POST", body: form });
  },
  triedThis: (
    techniqueId: string,
    data: {
      class_profile_id: string;
      label?: string | null;
      duration_minutes?: number;
      max_uses?: number | null;
    },
  ) =>
    request<RatingLink>(`/techniques/${techniqueId}/tried-this`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  createTechniqueRatingLink: (
    techniqueId: string,
    data: {
      class_profile_id?: string | null;
      label?: string | null;
      duration_minutes?: number;
      max_uses?: number | null;
    },
  ) =>
    request<RatingLink>(`/techniques/${techniqueId}/rating-links`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  previewRate: (token: string) => request<Technique>(`/rate/${token}`),
  submitRate: (token: string, data: TechniqueRatingCreate) =>
    request<{ id: string; technique_id: string; rating: number; comment: string | null }>(
      `/rate/${token}`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  // --- technique search & planning ---
  parseTechniqueSearch: (data: {
    class_profile_id: string;
    concept_text: string;
    problem_text: string;
    round?: number;
  }) =>
    request<TechniqueSearchParseResponse>("/technique-search/parse", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  refineTechniqueSearch: (data: {
    class_profile_id: string;
    concept_chips?: { id?: string | null; label: string }[];
    problem_chips?: string[];
    problem_types?: string[];
    selected_option_ids?: string[];
    round?: number;
  }) =>
    request<TechniqueSearchParseResponse>("/technique-search/refine", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  runTechniqueSearch: (data: {
    class_profile_id: string;
    concept_ids?: string[];
    concept_labels?: string[];
    problem_types?: string[];
    problem_text?: string | null;
    limit?: number;
  }) =>
    request<TechniqueSearchRunResponse>("/technique-search/run", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  planningMode: (params: {
    class_profile_id: string;
    concept_id?: string;
    concept_label?: string;
  }) => request<PlanningResponse>("/technique-search/planning", { query: params }),

  // --- system ---
  health: () => request<{ status: string; database: string }>("/health"),
};
