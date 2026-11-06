// Domain operations on top of db.js. Views only talk to this file (and auth.js).
//
// Everything is scoped to the "current organization" set by useOrg() at login. Records from
// other orgs are invisible: list*() filters them out and get*() returns null for them.
import * as db from './db.js';
import { DEFAULT_SETTINGS } from './retention.js';

// randomUUID needs a secure context (https/localhost); fall back so http://<LAN-ip> still works.
const uid = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
const now = () => new Date().toISOString();
export const newId = uid;

// ---------- org scope ----------
let orgId = null;
export const useOrg = (id) => {
  orgId = id || null;
};
export const currentOrgId = () => orgId;
const inOrg = (r) => !!r && !!orgId && r.orgId === orgId;
const all = async (store) => (await db.getAll(store)).filter(inOrg);
const one = async (store, id) => {
  if (!id) return null;
  const r = await db.get(store, id);
  return inOrg(r) ? r : null;
};
const put = (store, r) => db.put(store, { ...r, orgId: r.orgId || orgId });

// ---------- organizations ----------
export const listOrgs = async () => (await db.getAll('orgs')).sort((a, b) => a.name.localeCompare(b.name));
export const getOrg = (id) => (id ? db.get('orgs', id) : null);
export async function createOrg(name) {
  const org = { id: uid(), name: name.trim(), createdAt: now() };
  await db.put('orgs', org);
  return org;
}

// ---------- settings ----------
export async function getSettings() {
  const saved = (orgId && (await db.get('settings', `app:${orgId}`))) || {};
  return {
    ...DEFAULT_SETTINGS,
    ...saved,
    retentionDays: { ...DEFAULT_SETTINGS.retentionDays, ...(saved.retentionDays || {}) },
  };
}
export const saveSettings = (s) => db.put('settings', { ...s, key: `app:${orgId}` });

// ---------- images ----------
const urlCache = new Map();
export async function addImage(blob, kind) {
  const id = uid();
  await db.put('images', { id, blob, kind, createdAt: now() });
  return id;
}
export async function getImageUrl(id) {
  if (!id) return null;
  if (urlCache.has(id)) return urlCache.get(id);
  const rec = await db.get('images', id);
  if (!rec) return null;
  const url = URL.createObjectURL(rec.blob);
  urlCache.set(id, url);
  return url;
}
async function deleteImage(id) {
  if (urlCache.has(id)) {
    URL.revokeObjectURL(urlCache.get(id));
    urlCache.delete(id);
  }
  await db.del('images', id);
}

// ---------- members ----------
// member { id, orgId, name, aliases[], phone, email, trustedContacts[{ id, name, relationship, phone, address }],
//          userId?, registeredAt? }
export const listMembers = async () => (await all('members')).sort((a, b) => a.name.localeCompare(b.name));
export const getMember = (id) => one('members', id);
export async function saveMember(m) {
  const member = { id: m.id || uid(), name: '', aliases: [], phone: '', email: '', trustedContacts: [], ...m, orgId: m.orgId || orgId };
  await db.put('members', member);
  return member;
}

const norm = (s) =>
  (s || '')
    .toLowerCase()
    .replace(/[^a-z\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .sort()
    .join(' ');

// Match a name read off an envelope ("BRIGGS, DOROTHY", "Dot H Briggs") to the roster.
// Exact (order-insensitive) match against name or aliases; otherwise null and staff pick manually.
export function matchMember(name, members) {
  const n = norm(name);
  if (!n) return null;
  return members.find((m) => [m.name, ...(m.aliases || [])].some((x) => norm(x) === n)) || null;
}

// ---------- mail ----------
export const listMail = async () => (await all('mail')).sort((a, b) => b.receivedAt.localeCompare(a.receivedAt));
export const getMail = (id) => one('mail', id);
export const saveMail = (m) => put('mail', m);

// What a member can see: confirmed mail addressed to them (unconfirmed items may be mis-matched).
export const listMailForMember = async (memberId) =>
  (await listMail()).filter((m) => m.recipient.memberId === memberId && m.status !== 'needs_review');

export async function createMail({ front, back, processed }) {
  const [frontImageId, backImageId, members] = await Promise.all([
    addImage(front, 'front'),
    addImage(back, 'back'),
    listMembers(),
  ]);
  const member = matchMember(processed.recipient.name, members);
  const mail = {
    id: uid(),
    orgId,
    receivedAt: now(),
    frontImageId,
    backImageId,
    scanImageIds: [],
    sender: processed.sender,
    recipient: { name: processed.recipient.name, memberId: member?.id || null },
    notes: processed.notes,
    legibility: processed.legibility,
    illegibleReason: processed.illegibleReason || null,
    processing: processed.processing,
    // Everything starts as needs_review: a person confirms before the member is notified.
    status: 'needs_review',
    outcome: null,
    extraDays: 0,
  };
  await db.put('mail', mail);
  return mail;
}

// Confirm the extracted data and notify the recipient (once).
export async function confirmMail(mail) {
  mail.status = 'ready';
  await saveMail(mail);
  if (mail.recipient.memberId && !mail.notifiedAt) await notify(mail);
}

async function notify(mail) {
  const member = await getMember(mail.recipient.memberId);
  if (!member) return;
  const from = mail.sender.organization || mail.sender.name || 'an unknown sender';
  // 'queued' only: actual delivery (in-app + SMS) is the backend's job.
  await put('notifications', {
    id: uid(),
    mailId: mail.id,
    memberId: member.id,
    channels: member.phone ? ['app', 'sms'] : ['app'],
    body: `You have new mail from ${from}. Please pick it up.`,
    status: 'queued',
    at: now(),
  });
  mail.notifiedAt = now();
  await saveMail(mail);
}

// outcome: 'picked_up' | 'redirected' | 'discarded'
export async function closeMail(id, outcome, extra = {}) {
  const mail = await getMail(id);
  Object.assign(mail, extra, { status: 'closed', outcome, closedAt: now() });
  if (outcome === 'discarded') {
    // Privacy: drop the photos and scans; keep a minimal record for audit.
    for (const imgId of [mail.frontImageId, mail.backImageId, ...mail.scanImageIds]) {
      if (imgId) await deleteImage(imgId);
    }
    mail.frontImageId = mail.backImageId = null;
    mail.scanImageIds = [];
  }
  await saveMail(mail);
  return mail;
}

// ---------- requests ----------
// type: 'extra_time' { days } | 'scan' {} | 'redirect' { proxyNames[], address, relationship?, phone?, contactId? }
export const listRequests = async () => (await all('requests')).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
export async function createRequest(mail, type, payload = {}) {
  const req = {
    id: uid(),
    orgId,
    mailId: mail.id,
    memberId: mail.recipient.memberId,
    type,
    status: 'open',
    payload,
    createdAt: now(),
  };
  await db.put('requests', req);
  return req;
}
export async function resolveRequest(req, status, note) {
  req.status = status;
  req.resolvedAt = now();
  await put('requests', req);
  if (note) await addMessage({ memberId: req.memberId, mailId: req.mailId, requestId: req.id, from: 'system', body: note });
}

// ---------- messaging ----------
// message { id, orgId, memberId, mailId|null, requestId|null, from: 'staff'|'member'|'system', body, at,
//           seenByStaff, seenByMember }
// mailId null = a general conversation between the member and staff.
export const listAllMessages = async () => (await all('messages')).sort((a, b) => a.at.localeCompare(b.at));
export const listMessages = async (mailId) => (await listAllMessages()).filter((m) => m.mailId === mailId);
export const listMemberMessages = async (memberId) => (await listAllMessages()).filter((m) => m.memberId === memberId);

export function addMessage({ memberId, mailId = null, requestId = null, from, body }) {
  return db.put('messages', {
    id: uid(),
    orgId,
    memberId,
    mailId,
    requestId,
    from,
    body,
    at: now(),
    seenByStaff: from !== 'member',
    seenByMember: from === 'member',
  });
}

// role 'staff' | 'member'. Pass mailId to only mark that item's thread.
export async function markSeen(role, memberId, mailId) {
  const field = role === 'staff' ? 'seenByStaff' : 'seenByMember';
  for (const m of await listMemberMessages(memberId)) {
    if (m[field] || (mailId !== undefined && m.mailId !== mailId)) continue;
    await db.put('messages', { ...m, [field]: true });
  }
}

export const listNotifications = async (mailId) =>
  (await all('notifications')).filter((n) => n.mailId === mailId).sort((a, b) => a.at.localeCompare(b.at));

// Delete this org's mail, members, requests, messages and member logins. Staff logins stay.
export async function wipeOrgData() {
  for (const m of await all('mail')) {
    for (const imgId of [m.frontImageId, m.backImageId, ...(m.scanImageIds || [])]) if (imgId) await deleteImage(imgId);
    await db.del('mail', m.id);
  }
  for (const s of ['members', 'requests', 'messages', 'notifications']) for (const r of await all(s)) await db.del(s, r.id);
  for (const u of await all('users')) if (u.role === 'member') await db.del('users', u.id);
}

export const wipeEverything = db.clearAll;
