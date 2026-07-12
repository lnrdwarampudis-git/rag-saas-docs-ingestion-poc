import { getCurrentAccessToken } from "./auth/AuthProvider";

export class ApiAuthError extends Error {}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getCurrentAccessToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    throw new ApiAuthError("Session expired or invalid. Please sign in again.");
  }
  return response;
}
