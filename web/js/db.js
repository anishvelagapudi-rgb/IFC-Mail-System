// Thin IndexedDB wrapper. This is the ONLY file that knows where data lives.
// To move to a real backend, replace these functions (or store.js) with API calls.
//
// Draft schema (exact schema still to be decided with the team):
//   images        { id, blob, kind: 'front'|'back'|'scan', createdAt }
//   mail          { id, receivedAt, frontImageId, backImageId, scanImageIds[],
//                   sender{ name, organization, type }, recipient{ name, memberId },
//                   notes[], legibility: 'clear'|'degraded'|'illegible'|null,
//                   processing{ source, error? }, status: 'needs_review'|'ready'|'closed',
//                   outcome: null|'picked_up'|'redirected'|'discarded', extraDays,
//                   redirectedTo?, closedAt?, notifiedAt? }
//   members       { id, name, aliases[], phone, trustedContacts[{ id, name, relationship, phone }] }
//   requests      { id, mailId, memberId, type: 'extra_time'|'scan'|'redirect',
//                   status: 'open'|'approved'|'declined'|'fulfilled', payload, createdAt, resolvedAt? }
//   messages      { id, mailId, requestId?, from: 'staff'|'member'|'system', body, at }
//   notifications { id, mailId, memberId, channels[], body, status: 'queued', at }
//   settings      { key: 'app:<orgId>', ...value }
//   orgs          { id, name, createdAt }
//   users         { id, username, passwordHash, salt, role: 'admin'|'member', orgId, memberId?, name, createdAt }
//
// Every org-owned record (mail, members, requests, messages, notifications) carries an orgId.

const STORES = ['images', 'mail', 'members', 'requests', 'messages', 'notifications', 'orgs', 'users'];
let dbPromise;

function open() {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open('ifc-mail-staff', 2);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const s of STORES) if (!db.objectStoreNames.contains(s)) db.createObjectStore(s, { keyPath: 'id' });
      if (!db.objectStoreNames.contains('settings')) db.createObjectStore('settings', { keyPath: 'key' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function run(store, mode, fn) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const tx = db.transaction(store, mode);
        const request = fn(tx.objectStore(store));
        tx.oncomplete = () => resolve(request?.result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      }),
  );
}

export const getAll = (store) => run(store, 'readonly', (o) => o.getAll());
export const get = (store, id) => run(store, 'readonly', (o) => o.get(id));
export const put = (store, value) => run(store, 'readwrite', (o) => o.put(value));
export const del = (store, id) => run(store, 'readwrite', (o) => o.delete(id));

export async function clearAll() {
  for (const s of [...STORES, 'settings']) await run(s, 'readwrite', (o) => o.clear());
}
