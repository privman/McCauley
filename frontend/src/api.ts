export const BACKEND = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export type User = { id: string; name: string; email: string; title: string | null };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  listUsers: () => req<User[]>("/auth/users"),
  login: (user_id: string) =>
    req<User>("/auth/login", { method: "POST", body: JSON.stringify({ user_id }) }),
  logout: () => req<{ ok: true }>("/auth/logout", { method: "POST" }),
  me: () => req<User>("/auth/me"),
};

export function wsUrl(path: string): string {
  const proto = BACKEND.startsWith("https") ? "wss" : "ws";
  const host = BACKEND.replace(/^https?:\/\//, "");
  return `${proto}://${host}${path}`;
}
