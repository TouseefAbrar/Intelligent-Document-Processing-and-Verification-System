import { api } from './api/client';

export interface AuthUser {
  name: string;
  email: string;
  provider: 'email';
}

const SESSION_KEY = 'eef.session';
const REMEMBER_KEY = 'eef.rememberedEmail';
const TOKEN_KEY = 'eef.token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function getSession(): AuthUser | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setSession(user: AuthUser, token?: string) {
  if (token) setToken(token);
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  } catch {
    /* ignore */
  }
}

export function clearSession() {
  clearToken();
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function getRememberedEmail(): string {
  try {
    return localStorage.getItem(REMEMBER_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setRememberedEmail(email: string) {
  try {
    localStorage.setItem(REMEMBER_KEY, email);
  } catch {
    /* ignore */
  }
}

export function clearRememberedEmail() {
  try {
    localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* ignore */
  }
}

export interface SignInResult {
  ok: boolean;
  error?: string;
  user?: AuthUser;
  token?: string;
}

export interface ResetResult {
  ok: boolean;
  error?: string;
  devResetLink?: string;
}

/**
 * The account lives in the shared production database — these calls hit the
 * backend (DATABASE_URL), so the same credentials work from any device/browser.
 */
export async function signInWithEmail(email: string, password: string): Promise<SignInResult> {
  try {
    const res = await api.login({ email: email.trim(), password });
    return {
      ok: true,
      user: { name: res.user.name, email: res.user.email, provider: 'email' },
      token: res.token,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function signUpWithEmail(email: string, name: string, password: string): Promise<SignInResult> {
  try {
    const res = await api.register({ email: email.trim(), name: name.trim(), password });
    return {
      ok: true,
      user: { name: res.user.name, email: res.user.email, provider: 'email' },
      token: res.token,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function forgotPassword(email: string): Promise<ResetResult> {
  try {
    const res = await api.forgotPassword(email.trim());
    return { ok: true, devResetLink: res.dev_reset_link ?? undefined };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function resetPassword(token: string, newPassword: string): Promise<ResetResult> {
  try {
    await api.resetPassword(token, newPassword);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('') || 'U';
}
