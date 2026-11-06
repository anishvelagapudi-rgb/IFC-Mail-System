// Fetch wrapper for the Flask API. Holds the Supabase session tokens and refreshes them.
// Tokens live in localStorage so a reload keeps you signed in; nothing else is stored in the browser.

const KEY = 'ifc-mail-tokens';
let tokens = null; // { access_token, refresh_token, expires_at }
let refreshing = null;

function load() {
  if (tokens) return tokens;
  try {
    tokens = JSON.parse(localStorage.getItem(KEY) || 'null');
  } catch {
    tokens = null;
  }
  return tokens;
}

export function setTokens(t) {
  tokens = t || null;
  try {
    if (t) localStorage.setItem(KEY, JSON.stringify(t));
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: session lasts until reload */
  }
}

export const hasSession = () => !!load()?.access_token;

async function refresh() {
  const t = load();
  if (!t?.refresh_token) throw new ApiError('Please sign in.', 401);
  refreshing ??= raw('POST', '/api/auth/refresh', { refresh_token: t.refresh_token }, false)
    .then(setTokens)
    .catch((err) => {
      setTokens(null);
      throw err;
    })
    .finally(() => (refreshing = null));
  return refreshing;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function raw(method, path, data, auth = true) {
  const headers = {};
  let body;
  if (data instanceof FormData) body = data;
  else if (data !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(data);
  }
  if (auth && load()?.access_token) headers.Authorization = `Bearer ${tokens.access_token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection.', 0);
  }
  const json = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(json?.error || `Server error (${res.status})`, res.status);
  return json;
}

// Refresh shortly before expiry, and once more if the server still says 401.
export async function call(method, path, data) {
  const t = load();
  if (t?.expires_at && t.expires_at * 1000 < Date.now() + 30_000) await refresh().catch(() => {});
  try {
    return await raw(method, path, data);
  } catch (err) {
    if (err.status !== 401 || !load()?.refresh_token) throw err;
    await refresh();
    return raw(method, path, data);
  }
}

export const get = (p) => call('GET', p);
export const post = (p, d = {}) => call('POST', p, d);
export const patch = (p, d) => call('PATCH', p, d);
export const put = (p, d) => call('PUT', p, d);
export const publicPost = (p, d) => raw('POST', p, d, false);
export const publicGet = (p) => raw('GET', p, undefined, false);
