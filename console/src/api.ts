const API = "";

export function getToken(): string | null {
  return sessionStorage.getItem("nanobot_token");
}

export function setToken(token: string, userId?: string) {
  sessionStorage.setItem("nanobot_token", token);
  if (userId !== undefined) sessionStorage.setItem("nanobot_user_id", userId);
}

export function getUserId(): string | null {
  return sessionStorage.getItem("nanobot_user_id");
}

export function clearToken() {
  sessionStorage.removeItem("nanobot_token");
  sessionStorage.removeItem("nanobot_user_id");
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

type ApiOpts = Omit<RequestInit, "body"> & { body?: object };

export async function api<T>(path: string, opts: ApiOpts = {}): Promise<T> {
  const { body, ...rest } = opts;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(rest.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(API + path, {
    ...rest,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/";
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  if (res.headers.get("content-type")?.includes("application/json"))
    return res.json();
  return res.text() as Promise<T>;
}

export async function login(userId: string, password: string) {
  const r = await api<{ token: string; user_id: string }>("/api/auth/login", {
    method: "POST",
    body: { user_id: userId, password },
  });
  return r;
}

export async function logout() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  clearToken();
}

export async function listSessions() {
  return api<{ key: string; session_id: string; title: string; updated_at?: string; created_at?: string }[]>("/api/sessions");
}

export async function createSession() {
  return api<{ session_id: string }>("/api/sessions", { method: "POST" });
}

export type SessionMessage = {
  role: string;
  content: string;
  attachment_paths?: string[];
};

export async function getSessionMessages(sessionId: string) {
  return api<{ messages: SessionMessage[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/messages`
  );
}

/** Fetch an uploaded file by path and return a blob URL (for history images). */
export async function fetchAttachmentBlobUrl(path: string): Promise<string> {
  const token = getToken();
  const res = await fetch(`${API}/api/upload/serve?path=${encodeURIComponent(path)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Failed to load attachment");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Trigger browser download for a file served at path (e.g. agent-sent files). */
export async function downloadAttachment(path: string, suggestedName?: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API}/api/upload/serve?path=${encodeURIComponent(path)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Failed to download file");
  const blob = await res.blob();
  const name = suggestedName ?? (path.replace(/^.*[/\\]/, "") || "download");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export async function uploadFiles(files: File[]) {
  const token = getToken();
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(API + "/api/upload", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/";
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ paths: string[] }>;
}

export async function transcribeVoice(file: File) {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(API + "/api/voice/transcribe", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/";
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ text: string }>;
}

export function streamChat(
  message: string,
  sessionId: string | null,
  mediaPaths: string[],
  onEvent: (event: string, data: string | object) => void
): () => void {
  const token = getToken();
  const body = { message, session_id: sessionId || undefined, media_urls: mediaPaths };
  const ac = new AbortController();
  fetch(API + "/api/chat/send", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: ac.signal,
  })
    .then((res) => {
      if (!res.ok) throw new Error(res.statusText);
      if (!res.body) throw new Error("No body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      function pump(): Promise<void> {
        return reader.read().then(({ done, value }) => {
          if (done) return;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";
          for (const part of parts) {
            const [head, data] = part.split("\ndata: ");
            const event = head.replace("event: ", "").trim();
            if (event && data !== undefined) {
              try {
                const parsed = JSON.parse(data);
                onEvent(event, parsed);
              } catch {
                onEvent(event, data);
              }
            }
          }
          return pump();
        });
      }
      return pump();
    })
    .catch((e) => onEvent("error", e?.message || String(e)));
  return () => ac.abort();
}
