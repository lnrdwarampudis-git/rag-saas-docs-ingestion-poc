export type AuthConfig = {
  issuer: string;
  client_id: string;
  realm: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint: string;
};

let cached: Promise<AuthConfig> | null = null;

export function getAuthConfig(): Promise<AuthConfig> {
  if (!cached) {
    cached = fetch("/api/v1/auth/config").then((response) => {
      if (!response.ok) {
        cached = null;
        throw new Error("Failed to load auth configuration from backend");
      }
      return response.json() as Promise<AuthConfig>;
    });
  }
  return cached;
}
