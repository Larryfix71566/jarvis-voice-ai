// Centralized console URLs, bearer headers, and once-per-load auth notice.
export const ADMIN_BASE: string =
  import.meta.env.VITE_JARVIS_ADMIN_URL ?? "http://127.0.0.1:7861";
export const BOT_OFFER_URL: string =
  (import.meta.env.VITE_JARVIS_BOT_URL ?? "http://127.0.0.1:7860") + "/api/offer";

const TOKEN_KEY = "jarvis_token";

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable in private browsing; the current field still works.
  }
}

export function authHeaders(): Headers {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

type AuthErrorFn = () => void;
const authErrorSubscribers = new Set<AuthErrorFn>();
let notified = false;

export function subscribeAuthError(fn: AuthErrorFn): () => void {
  authErrorSubscribers.add(fn);
  return () => authErrorSubscribers.delete(fn);
}

export async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("http") ? path : `${ADMIN_BASE}${path}`;
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { ...init, headers });
  if (response.status === 401 && !notified) {
    notified = true;
    authErrorSubscribers.forEach((subscriber) => subscriber());
  }
  return response;
}
