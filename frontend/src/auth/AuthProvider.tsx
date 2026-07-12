import React from "react";
import { getAuthConfig } from "./authConfig";
import { generateCodeChallenge, generateRandomString } from "./pkce";
import { AccessTokenClaims, decodeJwtPayload } from "./jwt";

type TokenSet = {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  expires_at: number; // epoch ms
};

type AuthState = {
  status: "loading" | "authenticated" | "unauthenticated";
  user: AccessTokenClaims | null;
  accessToken: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
};

const SESSION_KEY = "rag_auth_session";
const PKCE_VERIFIER_KEY = "rag_pkce_verifier";
const PKCE_STATE_KEY = "rag_pkce_state";
const REFRESH_SKEW_MS = 30_000; // refresh 30s before expiry

const AuthContext = React.createContext<AuthState | null>(null);

// Module-level mirror of the current access token so plain fetch() helpers
// outside of React components (see api.ts) can attach it without prop drilling.
let currentAccessToken: string | null = null;
export function getCurrentAccessToken(): string | null {
  return currentAccessToken;
}

function loadSession(): TokenSet | null {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TokenSet;
  } catch {
    return null;
  }
}

function saveSession(tokens: TokenSet | null) {
  if (tokens) {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens));
  } else {
    sessionStorage.removeItem(SESSION_KEY);
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<AuthState["status"]>("loading");
  const [user, setUser] = React.useState<AccessTokenClaims | null>(null);
  const [accessToken, setAccessTokenState] = React.useState<string | null>(null);
  const refreshTimer = React.useRef<number | null>(null);

  const applyTokens = React.useCallback((tokens: TokenSet) => {
    saveSession(tokens);
    currentAccessToken = tokens.access_token;
    setAccessTokenState(tokens.access_token);
    setUser(decodeJwtPayload(tokens.access_token));
    setStatus("authenticated");
    scheduleRefresh(tokens);
  }, []);

  const clearSession = React.useCallback(() => {
    saveSession(null);
    currentAccessToken = null;
    setAccessTokenState(null);
    setUser(null);
    setStatus("unauthenticated");
    if (refreshTimer.current) {
      window.clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    }
  }, []);

  const refresh = React.useCallback(
    async (refreshToken: string) => {
      try {
        const config = await getAuthConfig();
        const body = new URLSearchParams({
          grant_type: "refresh_token",
          refresh_token: refreshToken,
          client_id: config.client_id
        });
        const response = await fetch(config.token_endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body
        });
        if (!response.ok) {
          throw new Error("Refresh failed");
        }
        const payload = await response.json();
        applyTokens({
          access_token: payload.access_token,
          refresh_token: payload.refresh_token ?? refreshToken,
          id_token: payload.id_token,
          expires_at: Date.now() + payload.expires_in * 1000
        });
      } catch {
        // Refresh token expired or Keycloak unreachable -- fall back to a
        // clean, unauthenticated state rather than looping on a dead token.
        clearSession();
      }
    },
    [applyTokens, clearSession]
  );

  const scheduleRefresh = React.useCallback(
    (tokens: TokenSet) => {
      if (refreshTimer.current) {
        window.clearTimeout(refreshTimer.current);
      }
      if (!tokens.refresh_token) return;
      const delay = Math.max(tokens.expires_at - Date.now() - REFRESH_SKEW_MS, 1000);
      refreshTimer.current = window.setTimeout(() => {
        refresh(tokens.refresh_token as string);
      }, delay);
    },
    [refresh]
  );

  const login = React.useCallback(async () => {
    const config = await getAuthConfig();
    const codeVerifier = generateRandomString(64);
    const state = generateRandomString(32);
    const codeChallenge = await generateCodeChallenge(codeVerifier);

    sessionStorage.setItem(PKCE_VERIFIER_KEY, codeVerifier);
    sessionStorage.setItem(PKCE_STATE_KEY, state);

    const redirectUri = window.location.origin + "/";
    const params = new URLSearchParams({
      client_id: config.client_id,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: "openid profile email",
      code_challenge: codeChallenge,
      code_challenge_method: "S256",
      state
    });
    window.location.href = `${config.authorization_endpoint}?${params.toString()}`;
  }, []);

  const logout = React.useCallback(async () => {
    const tokens = loadSession();
    const config = await getAuthConfig().catch(() => null);
    clearSession();
    if (config && tokens?.id_token) {
      const params = new URLSearchParams({
        id_token_hint: tokens.id_token,
        post_logout_redirect_uri: window.location.origin + "/"
      });
      window.location.href = `${config.end_session_endpoint}?${params.toString()}`;
    }
  }, [clearSession]);

  // Handle the redirect back from Keycloak (?code=...&state=...), and
  // otherwise try to resume a session already sitting in sessionStorage.
  React.useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");
    const returnedState = url.searchParams.get("state");

    async function handleCallback(authCode: string) {
      const expectedState = sessionStorage.getItem(PKCE_STATE_KEY);
      const codeVerifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
      sessionStorage.removeItem(PKCE_STATE_KEY);
      sessionStorage.removeItem(PKCE_VERIFIER_KEY);

      // Always scrub the auth params from the URL, even on failure, so a
      // refresh doesn't replay a used/invalid authorization code.
      window.history.replaceState({}, "", window.location.pathname);

      if (!codeVerifier || returnedState !== expectedState) {
        setStatus("unauthenticated");
        return;
      }

      try {
        const config = await getAuthConfig();
        const body = new URLSearchParams({
          grant_type: "authorization_code",
          code: authCode,
          redirect_uri: window.location.origin + "/",
          client_id: config.client_id,
          code_verifier: codeVerifier
        });
        const response = await fetch(config.token_endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body
        });
        if (!response.ok) throw new Error("Token exchange failed");
        const payload = await response.json();
        applyTokens({
          access_token: payload.access_token,
          refresh_token: payload.refresh_token,
          id_token: payload.id_token,
          expires_at: Date.now() + payload.expires_in * 1000
        });
      } catch {
        setStatus("unauthenticated");
      }
    }

    if (code) {
      handleCallback(code);
      return;
    }

    const existing = loadSession();
    if (existing && existing.expires_at > Date.now() + REFRESH_SKEW_MS) {
      applyTokens(existing);
    } else if (existing?.refresh_token) {
      refresh(existing.refresh_token);
    } else {
      setStatus("unauthenticated");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: AuthState = { status, user, accessToken, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
