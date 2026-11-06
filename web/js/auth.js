// Sign-in through the Flask API, backed by Supabase Auth. Passwords never touch browser storage;
// only the session tokens are kept (see api.js). Roles and org come from the server on every load.
import * as api from './api.js';
import { clearCaches } from './store.js';

let session = null; // { userId, role, status, orgId, memberId, username, name, orgName }

export const USERNAME_RE = /^[a-z0-9._-]{3,32}$/;
export const MIN_PASSWORD = 8;

const cleanUsername = (u) => (u || '').trim().toLowerCase();

function validate(username, password) {
  if (!USERNAME_RE.test(cleanUsername(username))) throw new Error('Username: 3–32 characters, letters, numbers, . _ or -');
  if ((password || '').length < MIN_PASSWORD) throw new Error(`Password must be at least ${MIN_PASSWORD} characters.`);
}

async function loadSession() {
  clearCaches();
  session = await api.get('/api/me');
  return session;
}

export async function login(username, password) {
  if (!cleanUsername(username) || !password) throw new Error('Enter your username and password.');
  api.setTokens(await api.publicPost('/api/auth/login', { username: cleanUsername(username), password }));
  return loadSession();
}

// A member signs up with an existing org. The account stays pending until an admin approves it.
export async function registerMember({ orgId, username, password, profile }) {
  if (!orgId) throw new Error('Choose your organization.');
  if (!profile.name.trim()) throw new Error('Enter your full name.');
  validate(username, password);
  api.setTokens(await api.publicPost('/api/auth/register', { orgId, username: cleanUsername(username), password, profile }));
  return loadSession();
}

// Re-establish the session on page load from the stored tokens.
export async function restore() {
  if (session) return session;
  if (!api.hasSession()) return null;
  try {
    return await loadSession();
  } catch (err) {
    if (err.status === 401 || err.status === 403) {
      api.setTokens(null);
      return null;
    }
    throw err;
  }
}

// Re-read role/status from the server (e.g. after an admin approves a pending account).
export async function reload() {
  session = null;
  return restore();
}

export function logout() {
  if (session) api.post('/api/auth/logout').catch(() => {});
  session = null;
  api.setTokens(null);
  clearCaches();
}

export const current = () => session;

export async function listStaff() {
  return (await api.get('/api/accounts')).filter((u) => u.role === 'admin');
}

// Admins add staff logins for their own organization.
export async function createUser({ username, password, name = '' }) {
  validate(username, password);
  return api.post('/api/staff', { username: cleanUsername(username), password, name });
}

export async function changePassword(oldPassword, newPassword) {
  if ((newPassword || '').length < MIN_PASSWORD) throw new Error(`Password must be at least ${MIN_PASSWORD} characters.`);
  await api.post('/api/auth/password', { oldPassword, newPassword });
}
