export const BACKEND = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export type User = { id: string; name: string; email: string; title: string | null };

// Retry network errors (e.g. backend restarting in dev → ERR_CONNECTION_RESET,
// which surfaces as a TypeError from fetch). HTTP errors — anything where the
// server actually answered — are NOT retried; those are real and should
// propagate. Backoff doubles each attempt: 250, 500, 1000, 2000, 4000 ms.
const RETRY_DELAYS_MS = [250, 500, 1000, 2000, 4000];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${BACKEND}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
        ...init,
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return (await res.json()) as T;
    } catch (e) {
      const isNetworkError = e instanceof TypeError;
      if (!isNetworkError || attempt >= RETRY_DELAYS_MS.length) throw e;
      await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[attempt]));
    }
  }
}

export const api = {
  listUsers: () => req<User[]>("/auth/users"),
  login: (user_id: string) =>
    req<User>("/auth/login", { method: "POST", body: JSON.stringify({ user_id }) }),
  logout: () => req<{ ok: true }>("/auth/logout", { method: "POST" }),
  me: () => req<User>("/auth/me"),
};

export function wsUrl(path: string, params?: Record<string, string | undefined>): string {
  const proto = BACKEND.startsWith("https") ? "wss" : "ws";
  const host = BACKEND.replace(/^https?:\/\//, "");
  const url = `${proto}://${host}${path}`;
  if (!params) return url;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") query.set(k, v);
  }
  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}
