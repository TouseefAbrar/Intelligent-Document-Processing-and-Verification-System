export interface AuthUser {
  name: string;
  email: string;
  provider: 'email';
}

const SESSION_KEY = 'eef.session';
const REMEMBER_KEY = 'eef.rememberedEmail';
const USERS_KEY = 'eef.users';

type StoredUsers = Record<string, { name: string; password: string }>;

function loadUsers(): StoredUsers {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? (JSON.parse(raw) as StoredUsers) : {};
  } catch {
    return {};
  }
}

function saveUser(email: string, name: string, password: string) {
  const users = loadUsers();
  users[email.toLowerCase()] = { name, password };
  try {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
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

export function setSession(user: AuthUser) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  } catch {
    /* ignore */
  }
}

export function clearSession() {
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
}

export function signInWithEmail(email: string, password: string): SignInResult {
  const key = email.trim().toLowerCase();
  if (!key || !password) return { ok: false, error: 'Enter your email and password.' };
  const users = loadUsers();
  const account = users[key];
  if (!account) return { ok: false, error: 'No account found for this email. Try creating one.' };
  if (account.password !== password) return { ok: false, error: 'Incorrect password. Please try again.' };
  return { ok: true, user: { name: account.name, email: key, provider: 'email' } };
}

export function signUpWithEmail(email: string, name: string, password: string): SignInResult {
  const key = email.trim().toLowerCase();
  if (loadUsers()[key]) return { ok: false, error: 'An account with this email already exists. Sign in instead.' };
  saveUser(key, name.trim(), password);
  return { ok: true, user: { name: name.trim(), email: key, provider: 'email' } };
}

export function accountExists(email: string): boolean {
  return Boolean(loadUsers()[email.trim().toLowerCase()]);
}

export function resetPassword(email: string, newPassword: string): { ok: boolean; error?: string } {
  const key = email.trim().toLowerCase();
  if (!key || !newPassword) return { ok: false, error: 'Enter your email and a new password.' };
  if (newPassword.length < 8) return { ok: false, error: 'Password must be at least 8 characters.' };
  const users = loadUsers();
  if (!users[key]) return { ok: false, error: 'No account found for this email. Create an account first.' };
  users[key] = { ...users[key], password: newPassword };
  try {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
  } catch {
    return { ok: false, error: 'Could not save the new password. Try again.' };
  }
  return { ok: true };
}

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('') || 'U';
}
