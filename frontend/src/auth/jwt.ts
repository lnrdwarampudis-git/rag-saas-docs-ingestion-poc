export type AccessTokenClaims = {
  sub: string;
  preferred_username?: string;
  email?: string;
  tenant_id?: string;
  realm_access?: { roles: string[] };
  exp: number;
  iat: number;
};

export function decodeJwtPayload<T = AccessTokenClaims>(token: string): T {
  const [, payload] = token.split(".");
  const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  const json = decodeURIComponent(
    atob(padded)
      .split("")
      .map((char) => "%" + char.charCodeAt(0).toString(16).padStart(2, "0"))
      .join("")
  );
  return JSON.parse(json) as T;
}
