/** Thin typed wrapper over fetch. One place that knows about the token,
 *  the base URL, and how the API reports errors. */

import type {
  ChatTurn,
  Connection,
  Mentor,
  MentorSource,
  ProfileDraft,
  Conversation,
  Message,
  Page,
  Profile,
  ProfileInput,
  Rating,
  RecommendationResponse,
  RecommendedResource,
  Resource,
  ResourceSearchResponse,
  TeacherSearchResponse,
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

/** Mentor chat streams, so it bypasses `request()` and reads the body itself.
 *  EventSource is not an option: it cannot POST and cannot send the token. */
export interface ResearchedPage {
  url: string;
  title: string;
}

export interface MentorReplyEnd {
  /** The sources this reply actually cited, in the order it cited them. */
  citations: MentorSource[];
  /** Keys the model wrote that match no source. The server checks; we show
   *  them as unverified rather than pretending they are references. */
  unverified: string[];
  /** Pages looked up mid-answer. Deliberately separate from `citations`:
   *  those are the educator's own material, these are not. */
  researched: ResearchedPage[];
}

export async function streamMentorChat(
  slug: string,
  messages: ChatTurn[],
  options: {
    onDelta: (text: string) => void;
    onEnd?: (end: MentorReplyEnd) => void;
    /** Fires when the mentor starts looking something up. A search can add
     *  half a minute, and a silent spinner that long reads as a hang. */
    onSearching?: (query: string | null) => void;
    signal?: AbortSignal;
  },
): Promise<void> {
  const token = getToken();
  const response = await fetch(`${API_URL}/mentors/${slug}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages }),
    signal: options.signal,
  });

  if (!response.ok) {
    if (response.status === 401 && token) setToken(null);
    const text = await response.text();
    throw readError(response.status, text ? (JSON.parse(text) as unknown) : null);
  }
  if (!response.body) throw new ApiError(500, "This browser cannot read a streamed reply.");

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  /** Returns true when the stream said it was finished. */
  const handleFrame = (frame: string): boolean => {
    let event = "message";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      // A frame may carry several data lines; SSE joins them with a newline.
      else if (line.startsWith("data:")) data += (data ? "\n" : "") + line.slice(5).trim();
    }
    const payload = data
      ? (JSON.parse(data) as {
          text?: string;
          detail?: string;
          citations?: MentorSource[];
          unverified?: string[];
          researched?: ResearchedPage[];
          query?: string | null;
        })
      : {};
    if (event === "delta" && payload.text) options.onDelta(payload.text);
    if (event === "searching") options.onSearching?.(payload.query ?? null);
    // The 200 was sent before the model spoke, so a failure arrives in-band.
    if (event === "error") throw new ApiError(502, payload.detail ?? "The conversation dropped.");
    if (event === "done") {
      options.onEnd?.({
        citations: payload.citations ?? [],
        unverified: payload.unverified ?? [],
        researched: payload.researched ?? [],
      });
      return true;
    }
    return false;
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (frame.trim() && handleFrame(frame)) return;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    // Stops the request when the caller aborts or a frame threw.
    await reader.cancel().catch(() => {});
  }
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
  rate: (teacherId: string, rating: number, comment?: string) =>
    request<Rating>(`/teachers/${teacherId}/ratings`, {
      method: "POST",
      body: JSON.stringify({ rating, comment: comment || null }),
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

  // --- mentors ---
  mentors: () => request<Mentor[]>("/mentors"),
  mentor: (slug: string) => request<Mentor>(`/mentors/${slug}`),
  // The conversation itself streams - see streamMentorChat above.

  // --- system ---
  health: () => request<{ status: string; database: string }>("/health"),
};
