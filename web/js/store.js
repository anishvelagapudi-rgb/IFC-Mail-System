// Domain operations on top of db.js. Views only talk to this file.
import * as db from './db.js';
import { DEFAULT_SETTINGS } from './retention.js';

// randomUUID needs a secure context (https/localhost); fall back so http://<LAN-ip> still works.
const uid = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
const now = () => new Date().toISOString();

// ---------- settings ----------
export async function getSettings() {
  const saved = (await db.get('settings', 'app')) || {};
  return {
    ...DEFAULT_SETTINGS,
    ...saved,
    retentionDays: { ...DEFAULT_SETTINGS.retentionDays, ...(saved.retentionDays || {}) },
  };
}
export const saveSettings = (s) => db.put('settings', { ...s, key: 'app' });

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
export const listMembers = async () => (await db.getAll('members')).sort((a, b) => a.name.localeCompare(b.name));
export const getMember = (id) => (id ? db.get('members', id) : null);
export async function saveMember(m) {
  const member = { id: m.id || uid(), name: '', aliases: [], phone: '', trustedContacts: [], ...m };
  await db.put('members', member);
  return member;
}
export const newId = uid;

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
export const listMail = async () => (await db.getAll('mail')).sort((a, b) => b.receivedAt.localeCompare(a.receivedAt));
export const getMail = (id) => db.get('mail', id);
export const saveMail = (m) => db.put('mail', m);

export async function createMail({ front, back, processed }) {
  const [frontImageId, backImageId, members] = await Promise.all([
    addImage(front, 'front'),
    addImage(back, 'back'),
    listMembers(),
  ]);
  const member = matchMember(processed.recipient.name, members);
  const mail = {
    id: uid(),
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
  await db.put('notifications', {
    id: uid(),
    mailId: mail.id,
    memberId: member.id,
    channels: member.phone ? ['app', 'sms'] : ['app'],
    body: `You have new mail from ${from}. Please pick it up at IFC.`,
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
export const listRequests = async () => (await db.getAll('requests')).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
export async function createRequest(mail, type, payload = {}) {
  const req = {
    id: uid(),
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
  await db.put('requests', req);
  if (note) await addMessage(req.mailId, 'system', note, req.id);
}

// ---------- messaging ----------
export const listMessages = async (mailId) =>
  (await db.getAll('messages')).filter((m) => m.mailId === mailId).sort((a, b) => a.at.localeCompare(b.at));
export const addMessage = (mailId, from, body, requestId) =>
  db.put('messages', { id: uid(), mailId, requestId: requestId || null, from, body, at: now() });

export const listNotifications = async (mailId) =>
  (await db.getAll('notifications')).filter((n) => n.mailId === mailId).sort((a, b) => a.at.localeCompare(b.at));

export const wipeEverything = db.clearAll;
