import { Page } from "@playwright/test";

function base64UrlEncode(json: object): string {
  const raw = Buffer.from(JSON.stringify(json)).toString("base64");
  return raw.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Seeds sessionStorage with a fake-but-well-formed access token before the
 * page loads, so tests exercise the authenticated workspace without needing
 * a live Keycloak + PKCE round trip. The frontend only decodes this token
 * client-side for display -- real verification happens on the backend, which
 * these UI smoke tests don't call.
 */
export async function signInAsFixtureUser(
  page: Page,
  overrides: { roles?: string[]; username?: string; tenantId?: string } = {}
) {
  const header = base64UrlEncode({ alg: "none", typ: "JWT" });
  const payload = base64UrlEncode({
    sub: "fixture-user",
    preferred_username: overrides.username ?? "fixture-user",
    email: "fixture-user@example.test",
    tenant_id: overrides.tenantId ?? "00000000-0000-4000-8000-000000000001",
    realm_access: { roles: overrides.roles ?? ["admin"] },
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600
  });
  const fakeToken = `${header}.${payload}.fixture-signature`;

  await page.addInitScript(
    ({ token, expiresAt }) => {
      window.sessionStorage.setItem(
        "rag_auth_session",
        JSON.stringify({ access_token: token, expires_at: expiresAt })
      );
    },
    { token: fakeToken, expiresAt: Date.now() + 3600 * 1000 }
  );
}
