// Thin API client. The Vite dev server proxies /api/* to FastAPI (see vite.config.ts).
// Auth: JWT bearer token, persisted in localStorage, attached to every request.

// ponytail: API payloads are `any` — backend Pydantic schemas are the source of
// truth; generate types from the OpenAPI spec if drift ever bites.
type Json = any;

export type ToastFn = (message: string, type?: "info" | "success" | "error") => void;
export type Resume = { id: number; filename: string };

const TOKEN_KEY = "ajagent_token";

export const auth = {
  getToken: (): string | null => localStorage.getItem(TOKEN_KEY),
  setToken: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request(path: string, options: RequestInit = {}): Promise<Json> {
  const headers: Record<string, string> = { ...((options.headers as Record<string, string>) || {}) };
  const token = auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, { ...options, headers });
  let body: Json = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON response */
  }
  if (res.status === 401 && !path.startsWith("/auth/")) {
    auth.clear();
    onUnauthorized?.();
    throw new Error("Session expired — please log in again.");
  }
  if (!res.ok) {
    const detail = body?.detail || `Request failed (${res.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

export const api = {
  health: () => request("/health"),

  // Auth
  signup: (email: string, password: string) =>
    request("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request("/auth/login", {
      method: "POST",
      // OAuth2 password flow: form-encoded, email travels as `username`
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    }),
  me: () => request("/auth/me"),

  // Resume pipeline
  listResumes: () => request("/resumes"),
  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request("/resumes/upload", { method: "POST", body: form });
  },
  extract: (resumeId: number) => request(`/resumes/${resumeId}/extract`, { method: "POST" }),
  parse: (resumeId: number) => request(`/resumes/${resumeId}/parse`, { method: "POST" }),
  embed: (resumeId: number) => request(`/resumes/${resumeId}/embed`, { method: "POST" }),

  // Jobs
  ingestJobs: ({ query, sources, country, location, results }: {
    query: string; sources: string; country: string; location?: string; results: number;
  }) => {
    const params = new URLSearchParams({ query, sources, country, results: String(results) });
    if (location) params.set("location", location);
    return request(`/jobs/ingest?${params}`, { method: "POST" });
  },
  embedPending: () => request("/jobs/embed-pending", { method: "POST" }),

  // Matching
  generateMatches: (resumeId: number, { location, minSalary }: { location?: string; minSalary?: number } = {}) => {
    const params = new URLSearchParams();
    if (location) params.set("location_contains", location);
    if (minSalary) params.set("min_salary", String(minSalary));
    const qs = params.toString();
    return request(`/resumes/${resumeId}/matches/generate${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
  listMatches: (resumeId: number, status?: string) => {
    const qs = status ? `?status=${status}` : "";
    return request(`/resumes/${resumeId}/matches${qs}`);
  },
  setMatchStatus: (matchId: number, status: string) =>
    request(`/resumes/matches/${matchId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),

  // Tailoring
  tailorMatch: (matchId: number) => request(`/resumes/matches/${matchId}/tailor`, { method: "POST" }),
  coverLetter: (matchId: number) => request(`/resumes/matches/${matchId}/cover-letter`, { method: "POST" }),

  // Preferences (the assistant's standing instructions)
  getPreferences: () => request("/preferences"),
  savePreferences: (prefs: Json) =>
    request("/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    }),

  // Assistant (LangGraph agent)
  assistantChat: (message: string) =>
    request("/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  assistantRun: () => request("/assistant/run", { method: "POST" }),
  assistantRuns: (limit = 10) => request(`/assistant/runs?limit=${limit}`),

  // Applications (prepared packages awaiting approval)
  listApplications: (status?: string) =>
    request(`/applications${status ? `?status=${status}` : ""}`),
  setApplicationStatus: (applicationId: number, status: string) =>
    request(`/applications/${applicationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
};
