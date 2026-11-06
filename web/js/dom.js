// Tiny DOM helpers. All user data goes through text nodes / setAttribute, never innerHTML.

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'value') value = v; // set after children so <select> works
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  if (value !== undefined) el.value = value;
  return el;
}

export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';

export const fmtDay = (d) =>
  d ? new Date(d).toLocaleDateString([], { dateStyle: 'medium' }) : '—';

export const daysUntil = (d) => Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);

// <input type="datetime-local"> wants local time without a zone suffix.
export function toLocalInput(iso) {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export const fromLocalInput = (v) => new Date(v).toISOString();

export function toast(msg, kind = 'ok') {
  let host = document.getElementById('toasts');
  if (!host) {
    host = h('div', { id: 'toasts', 'aria-live': 'polite' });
    document.body.append(host);
  }
  const t = h('div', { class: `toast ${kind}` }, msg);
  host.append(t);
  setTimeout(() => t.remove(), 4000);
}

export function badge(text, kind = '') {
  return h('span', { class: `badge ${kind}` }, text);
}

export function emptyState(text) {
  return h('p', { class: 'empty' }, text);
}
