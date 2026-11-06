// Domain operations. Views only talk to this file (and auth.js).
//
// Everything goes through the Flask API (api.js). The server decides what the signed-in user
// may see: admins get their organization's data, members only their own. Function names and
// return shapes match the old browser-only version so the views did not have to change.
import * as api from './api.js';
import { DEFAULT_SETTINGS } from './retention.js';

const q = (params) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString();
  return s ? `?${s}` : '';
};
const orNull = (p) => p.catch((err) => (err.status === 404 ? null : Promise.reject(err)));
const byDesc = (k) => (a, b) => (b[k] || '').localeCompare(a[k] || '');

// Ids for new trusted contacts are made in the browser so a forward request can point at one
// before it is saved. The server accepts them (they must be UUIDs).
export const newId = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));

// ---------- organizations ----------
export const listOrgs = () => api.publicGet('/api/orgs');

// ---------- settings ----------
let settingsCache = null; // { at, value }
export async function getSettings() {
  if (settingsCache && Date.now() - settingsCache.at < 60_000) return structuredClone(settingsCache.value);
  const s = await api.get('/api/settings');
  const value = { ...DEFAULT_SETTINGS, ...s, retentionDays: { ...DEFAULT_SETTINGS.retentionDays, ...s.retentionDays } };
  settingsCache = { at: Date.now(), value };
  return structuredClone(value);
}
export async function saveSettings(s) {
  settingsCache = null;
  return api.put('/api/settings', { retentionDays: s.retentionDays, followupAfterDays: s.followupAfterDays, minConfidence: s.minConfidence });
}
export const clearCaches = () => (settingsCache = null);

// ---------- images ----------
// Mail objects carry short-lived signed URLs in frontImageId / backImageId / scanImageIds.
export const getImageUrl = async (id) => id || null;

// ---------- members ----------
// member { id, orgId, name, aliases[], phone, email, trustedContacts[{ id, name, relationship, phone, address }],
//          userId?, registeredAt? }
export const listMembers = () => api.get('/api/members');
export const getMember = (id) => (id ? orNull(api.get(`/api/members/${encodeURIComponent(id)}`)) : Promise.resolve(null));
export async function saveMember(m) {
  const data = { name: m.name, aliases: m.aliases || [], phone: m.phone || '', email: m.email || '', trustedContacts: m.trustedContacts || [] };
  const saved = m.id ? await api.patch(`/api/members/${encodeURIComponent(m.id)}`, data) : await api.post('/api/members', data);
  return Object.assign(m, saved);
}

const norm = (s) =>
  (s || '')
    .toLowerCase()
    .replace(/[^a-z\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .sort()
    .join(' ');

// Match a name read off an envelope ("BRIGGS, DOROTHY") to the roster while staff type.
// Exact (order-insensitive) match against name or aliases; the server also tries a strict fuzzy match.
export function matchMember(name, members) {
  const n = norm(name);
  if (!n) return null;
  return members.find((m) => [m.name, ...(m.aliases || [])].some((x) => norm(x) === n)) || null;
}

// ---------- accounts (admin) ----------
// account { id, username, name, role: 'admin'|'member', status: 'pending'|'active'|'rejected', memberId, registration, createdAt }
export const listAccounts = () => api.get('/api/accounts');
export const approveAccount = (userId, memberId = null) => api.post(`/api/accounts/${encodeURIComponent(userId)}/approve`, { memberId });
export const rejectAccount = (userId) => api.post(`/api/accounts/${encodeURIComponent(userId)}/reject`);

// ---------- mail ----------
export const listMail = async () => (await api.get('/api/mail')).sort(byDesc('receivedAt'));
export const getMail = (id) => orNull(api.get(`/api/mail/${encodeURIComponent(id)}`));

// What a member can see: confirmed mail addressed to them. The server applies the filter.
export const listMailForMember = () => listMail();

// Staff edits from the review screen (sender, recipient, notes, legibility, date, extra days).
export async function saveMail(m) {
  const saved = await api.patch(`/api/mail/${encodeURIComponent(m.id)}`, {
    sender: m.sender,
    recipient: m.recipient,
    notes: m.notes,
    legibility: m.legibility,
    illegibleReason: m.illegibleReason,
    receivedAt: m.receivedAt,
    extraDays: m.extraDays || 0,
  });
  return Object.assign(m, saved);
}

// Upload both photos; the server stores them privately, runs the pipeline and matches the recipient.
export async function createMail({ front, back }) {
  const body = new FormData();
  body.append('front', front, 'front.jpg');
  body.append('back', back, 'back.jpg');
  return api.post('/api/mail', body);
}

// Confirm the extracted data and notify the recipient (once).
export async function confirmMail(mail) {
  await saveMail(mail);
  return Object.assign(mail, await api.post(`/api/mail/${encodeURIComponent(mail.id)}/confirm`));
}

// outcome: 'picked_up' | 'redirected' | 'discarded'. Discarding deletes the photos.
export const closeMail = (id, outcome, extra = {}) => api.post(`/api/mail/${encodeURIComponent(id)}/close`, { outcome, ...extra });

// A photo of the contents for a member who asked for one.
export async function addScan(mail, blob) {
  const body = new FormData();
  body.append('file', blob, 'scan.jpg');
  return Object.assign(mail, await api.post(`/api/mail/${encodeURIComponent(mail.id)}/scans`, body));
}

// ---------- requests ----------
// type: 'extra_time' { days } | 'scan' {} | 'redirect' { proxyNames[], address, relationship?, phone?, contactId? }
export const listRequests = async () => (await api.get('/api/requests')).sort(byDesc('createdAt'));
export const createRequest = (mail, type, payload = {}) => api.post('/api/requests', { mailId: mail.id, type, payload });
export async function resolveRequest(req, status, note) {
  return Object.assign(req, await api.post(`/api/requests/${encodeURIComponent(req.id)}/resolve`, { status, note }));
}

// ---------- messaging ----------
// message { id, orgId, memberId, mailId|null, requestId|null, from: 'staff'|'member'|'system', body, at,
//           seenByStaff, seenByMember }
export const listAllMessages = () => api.get('/api/messages');
export const listMessages = (mailId) => api.get(`/api/messages${q({ mailId })}`);
export const listMemberMessages = (memberId) => api.get(`/api/messages${q({ memberId })}`);

// `from` is decided by the server from who is signed in.
export const addMessage = ({ memberId, mailId = null, requestId = null, body }) => api.post('/api/messages', { memberId, mailId, requestId, body });

// role is implied by the signed-in user. Pass mailId to only mark that item's thread.
export function markSeen(_role, memberId, mailId) {
  return api.post('/api/messages/seen', mailId === undefined ? { memberId } : { memberId, mailId });
}

export const listNotifications = (mailId) => api.get(`/api/mail/${encodeURIComponent(mailId)}/notifications`);

// ---------- follow-up (admin) ----------
export const listFollowups = () => api.get('/api/followup');
export const logFollowup = (mailId, { channel, outcome, note }) => api.post(`/api/followup/${encodeURIComponent(mailId)}/log`, { channel, outcome, note });
export const sendFollowupText = (mailId, body) => api.post(`/api/followup/${encodeURIComponent(mailId)}/text`, { body });

// Delete this org's mail, photos, members, requests, messages and member logins. Staff logins stay.
export const wipeOrgData = () => api.post('/api/org/wipe', { confirm: 'DELETE' });
