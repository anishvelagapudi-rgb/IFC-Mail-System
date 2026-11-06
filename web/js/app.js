import { h } from './dom.js';
import * as store from './store.js';
import { discardAfter } from './retention.js';
import { inboxView } from './views/inbox.js';
import { captureView } from './views/capture.js';
import { detailView } from './views/detail.js';
import { requestsView } from './views/requests.js';
import { discardView } from './views/discard.js';
import { membersView } from './views/members.js';
import { settingsView } from './views/settings.js';

const routes = [
  [/^\/$/, () => inboxView(), '/'],
  [/^\/capture$/, () => captureView(), '/capture'],
  [/^\/mail\/([^/]+)$/, (id) => detailView(id), '/'],
  [/^\/requests$/, () => requestsView(), '/requests'],
  [/^\/discard$/, () => discardView(), '/discard'],
  [/^\/members$/, () => membersView(), '/members'],
  [/^\/settings$/, () => settingsView(), '/settings'],
];

const NAV = [
  ['/', 'Inbox', 'review'],
  ['/capture', 'Scan', null],
  ['/requests', 'Requests', 'requests'],
  ['/discard', 'Discard', 'discard'],
  ['/members', 'Members', null],
  ['/settings', 'Settings', null],
];

const main = document.getElementById('main');
const nav = document.getElementById('nav');
let current = null;

async function counts() {
  const [mail, requests, settings] = await Promise.all([store.listMail(), store.listRequests(), store.getSettings()]);
  const active = mail.filter((m) => m.status !== 'closed');
  const ids = new Set(active.map((m) => m.id));
  return {
    review: active.filter((m) => m.status === 'needs_review').length,
    requests: requests.filter((r) => r.status === 'open' && ids.has(r.mailId)).length,
    discard: active.filter((m) => discardAfter(m, settings) <= new Date()).length,
  };
}

async function renderNav(activePath) {
  const c = await counts();
  nav.replaceChildren(
    ...NAV.map(([path, label, key]) =>
      h('a', { href: `#${path}`, class: path === activePath ? 'on' : '', 'aria-current': path === activePath ? 'page' : null }, label, key && c[key] ? h('span', { class: 'pill' }, c[key]) : null),
    ),
  );
}

async function route() {
  current?.destroy?.(); // e.g. release the camera
  const path = location.hash.slice(1) || '/';
  for (const [re, make, navPath] of routes) {
    const m = path.match(re);
    if (!m) continue;
    current = make(...m.slice(1).map(decodeURIComponent));
    main.replaceChildren(current);
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    renderNav(navPath);
    return;
  }
  location.hash = '#/';
}

window.addEventListener('hashchange', route);
route();
