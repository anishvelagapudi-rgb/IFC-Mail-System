// TEMPORARY login system. Accounts and password hashes live in this browser's IndexedDB, and
// the check happens in client code, so anyone with access to the device can bypass it.
// It exists so the two sides of the app (org admins vs. members) can be built and tested.
// Replace with server-side auth (and real password hashing, e.g. argon2/bcrypt) with the backend.
import * as db from './db.js';
import * as store from './store.js';

const KEY = 'ifc-mail-session';
let session = null; // { userId, role, orgId, memberId, username, name, orgName }

export const USERNAME_RE = /^[a-z0-9._-]{3,32}$/;
export const MIN_PASSWORD = 6;

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');

// SHA-256 needs a secure context (localhost/https). Over plain http on a LAN we fall back to a
// non-cryptographic hash, tagged so the two are never compared with each other.
async function hashPassword(password, salt) {
  const data = `${salt}:${password}`;
  if (crypto.subtle) return 'sha256:' + hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data)));
  let h = 0x811c9dc5;
  for (let i = 0; i < data.length; i++) h = Math.imul(h ^ data.charCodeAt(i), 0x01000193) >>> 0;
  return 'fnv:' + h.toString(16);
}

async function verify(user, password) {
  if (user.passwordHash.startsWith('sha256:') && !crypto.subtle) {
    throw new Error('Open the app on localhost or https to sign in.');
  }
  return (await hashPassword(password, user.salt)) === user.passwordHash;
}

const cleanUsername = (u) => (u || '').trim().toLowerCase();

async function findUser(username) {
  const u = cleanUsername(username);
  return (await db.getAll('users')).find((x) => x.username === u) || null;
}

function validate(username, password) {
  if (!USERNAME_RE.test(cleanUsername(username))) throw new Error('Username: 3–32 characters, letters, numbers, . _ or -');
  if ((password || '').length < MIN_PASSWORD) throw new Error(`Password must be at least ${MIN_PASSWORD} characters.`);
}

export async function createUser({ username, password, role, orgId, memberId = null, name = '' }) {
  validate(username, password);
  if (await findUser(username)) throw new Error('That username is taken.');
  const salt = store.newId();
  const user = {
    id: store.newId(),
    username: cleanUsername(username),
    salt,
    passwordHash: await hashPassword(password, salt),
    role,
    orgId,
    memberId,
    name,
    createdAt: new Date().toISOString(),
  };
  await db.put('users', user);
  return user;
}

// A new org plus its first admin account.
export async function registerOrg({ orgName, name, username, password }) {
  if (!orgName.trim()) throw new Error('Enter the organization name.');
  validate(username, password);
  if (await findUser(username)) throw new Error('That username is taken.');
  const org = await store.createOrg(orgName);
  const user = await createUser({ username, password, role: 'admin', orgId: org.id, name: name.trim() });
  return startSession(user);
}

// A member signs up with an existing org. Creates their member profile too.
export async function registerMember({ orgId, username, password, profile }) {
  if (!(await store.getOrg(orgId))) throw new Error('Choose your organization.');
  if (!profile.name.trim()) throw new Error('Enter your full name.');
  validate(username, password);
  if (await findUser(username)) throw new Error('That username is taken.');
  store.useOrg(orgId);
  const member = await store.saveMember({ ...profile, orgId, registeredAt: new Date().toISOString() });
  const user = await createUser({ username, password, role: 'member', orgId, memberId: member.id, name: member.name });
  member.userId = user.id;
  await store.saveMember(member);
  return startSession(user);
}

export async function login(username, password) {
  const user = await findUser(username);
  if (!user || !(await verify(user, password))) throw new Error('Wrong username or password.');
  return startSession(user);
}

async function startSession(user) {
  const org = await store.getOrg(user.orgId);
  session = { userId: user.id, role: user.role, orgId: user.orgId, memberId: user.memberId, username: user.username, name: user.name, orgName: org?.name || '' };
  store.useOrg(user.orgId);
  try {
    localStorage.setItem(KEY, JSON.stringify({ userId: user.id }));
  } catch {
    /* private mode: session lasts until reload */
  }
  return session;
}

// Re-establish the session on page load. The stored value is only a user id; role and org are
// always re-read from the user record.
export async function restore() {
  if (session) return session;
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  } catch {
    saved = null;
  }
  const user = saved?.userId ? await db.get('users', saved.userId) : null;
  return user ? startSession(user) : null;
}

export function logout() {
  session = null;
  store.useOrg(null);
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export const current = () => session;

export async function listStaff() {
  return (await db.getAll('users')).filter((u) => u.orgId === session?.orgId && u.role === 'admin');
}

export async function changePassword(oldPassword, newPassword) {
  const user = await db.get('users', session.userId);
  if (!(await verify(user, oldPassword))) throw new Error('Current password is wrong.');
  validate(user.username, newPassword);
  user.salt = store.newId();
  user.passwordHash = await hashPassword(newPassword, user.salt);
  await db.put('users', user);
}
