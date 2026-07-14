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

export function apiUploadWithProgress(
  path: string,
  body: FormData,
  onProgress: (percent: number) => void
): Promise<Response> {
  const token = getCurrentAccessToken();
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", path);
    if (token) {
      request.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      const response = new Response(request.responseText, {
        status: request.status,
        statusText: request.statusText
      });
      if (request.status === 401) {
        reject(new ApiAuthError("Session expired or invalid. Please sign in again."));
        return;
      }
      resolve(response);
    };
    request.onerror = () => reject(new Error("Upload failed before the server responded."));
    request.onabort = () => reject(new Error("Upload was cancelled."));
    request.send(body);
  });
}
