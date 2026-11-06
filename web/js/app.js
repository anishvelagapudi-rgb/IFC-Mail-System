import { h, toast } from './dom.js';
import * as store from './store.js';
import * as auth from './auth.js';
import { discardAfter } from './retention.js';
import { loginView } from './views/login.js';
import { inboxView } from './views/inbox.js';
import { captureView } from './views/capture.js';
import { detailView } from './views/detail.js';
import { requestsView } from './views/requests.js';
import { discardView } from './views/discard.js';
import { membersView } from './views/members.js';
import { settingsView } from './views/settings.js';
import { messagesView, conversationView } from './views/messages.js';
import { followupView, pendingView } from './views/followup.js';
import { memberMailListView } from './views/member/mail-list.js';
import { memberMailDetailView } from './views/member/mail-detail.js';
import { memberMessagesView } from './views/member/messages.js';
import { memberProfileView } from './views/member/profile.js';

const refreshNav = () => renderNav(currentNav);

// [pattern, view factory, which nav item to highlight]
const STAFF_ROUTES = [
  [/^\/$/, () => inboxView(), '/'],
  [/^\/capture$/, () => captureView(), '/capture'],
  [/^\/mail\/([^/]+)$/, (id) => detailView(id), '/'],
  [/^\/requests$/, () => requestsView(), '/requests'],
  [/^\/messages$/, () => messagesView(), '/messages'],
  [/^\/messages\/([^/]+)$/, (id) => conversationView(id, refreshNav), '/messages'],
  [/^\/discard$/, () => discardView(), '/discard'],
  [/^\/followup$/, () => followupView(), '/followup'],
  [/^\/members(?:\/([^/]+))?$/, (id) => membersView(id), '/members'],
  [/^\/settings$/, () => settingsView(), '/settings'],
];
const STAFF_NAV = [
  ['/', 'Inbox', 'review'],
  ['/capture', 'Scan', null],
  ['/requests', 'Requests', 'requests'],
  ['/messages', 'Messages', 'unread'],
  ['/followup', 'Follow-up', null],
  ['/discard', 'Discard', 'discard'],
  ['/members', 'Members', 'pending'],
  ['/settings', 'Settings', null],
];

const MEMBER_ROUTES = [
  [/^\/$/, () => memberMailListView(), '/'],
  [/^\/mail\/([^/]+)$/, (id) => memberMailDetailView(id), '/'],
  [/^\/messages$/, () => memberMessagesView(refreshNav), '/messages'],
  [/^\/account$/, () => memberProfileView(), '/account'],
];
const MEMBER_NAV = [
  ['/', 'My mail', 'waiting'],
  ['/messages', 'Messages', 'unread'],
  ['/account', 'My account', null],
];

const main = document.getElementById('main');
const nav = document.getElementById('nav');
const who = document.getElementById('who');
const brandRole = document.getElementById('brand-role');
let current = null;
let currentNav = '/';

async function staffCounts() {
  const [mail, requests, settings, messages, accounts] = await Promise.all([store.listMail(), store.listRequests(), store.getSettings(), store.listAllMessages(), store.listAccounts()]);
  const active = mail.filter((m) => m.status !== 'closed');
  const ids = new Set(active.map((m) => m.id));
  return {
    review: active.filter((m) => m.status === 'needs_review').length,
    requests: requests.filter((r) => r.status === 'open' && ids.has(r.mailId)).length,
    discard: active.filter((m) => discardAfter(m, settings) <= new Date()).length,
    unread: messages.filter((m) => !m.seenByStaff).length,
    pending: accounts.filter((a) => a.status === 'pending').length,
  };
}

async function memberCounts(memberId) {
  const [mail, messages] = await Promise.all([store.listMailForMember(memberId), store.listMemberMessages(memberId)]);
  return { waiting: mail.filter((m) => m.status !== 'closed').length, unread: messages.filter((m) => !m.seenByMember).length };
}

async function renderNav(activePath) {
  currentNav = activePath;
  const s = auth.current();
  if (!s) {
    nav.replaceChildren();
    who.replaceChildren();
    brandRole.textContent = '';
    return;
  }
  const isStaff = s.role === 'admin';
  const c = s.status !== 'active' ? {} : await (isStaff ? staffCounts() : memberCounts(s.memberId)).catch(() => ({}));
  brandRole.textContent = isStaff ? 'staff' : '';
  nav.replaceChildren(
    ...(s.status !== 'active' ? [] : isStaff ? STAFF_NAV : MEMBER_NAV).map(([path, label, key]) =>
      h('a', { href: `#${path}`, class: path === activePath ? 'on' : '', 'aria-current': path === activePath ? 'page' : null }, label, key && c[key] ? h('span', { class: 'pill' }, c[key]) : null),
    ),
  );
  who.replaceChildren(
    h('span', { class: 'who-name' }, `${s.name || s.username}${s.orgName ? ` · ${s.orgName}` : ''}`),
    h('button', { class: 'btn ghost', type: 'button', onclick: () => {
      auth.logout();
      goHome();
    } }, 'Log out'),
  );
}

function show(view, navPath) {
  current?.destroy?.(); // e.g. release the camera
  current = view;
  main.replaceChildren(view);
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
  renderNav(navPath);
}

async function route() {
  let s;
  try {
    s = await auth.restore();
  } catch (err) {
    main.replaceChildren(h('section', { class: 'view' }, h('h1', null, 'Cannot reach IFC Mail'), h('p', null, err.message), h('button', { class: 'btn', type: 'button', onclick: route }, 'Try again')));
    return;
  }
  if (!s) {
    show(loginView('login', goHome), null);
    return;
  }
  if (s.status !== 'active') {
    show(pendingView(s, async () => ((await auth.reload())?.status === 'active' ? goHome() : toast('Not approved yet. Please check with staff.', 'warn'))), null);
    return;
  }
  const path = location.hash.slice(1) || '/';
  for (const [re, make, navPath] of s.role === 'admin' ? STAFF_ROUTES : MEMBER_ROUTES) {
    const m = path.match(re);
    if (!m) continue;
    show(make(...m.slice(1).map((x) => (x == null ? x : decodeURIComponent(x)))), navPath);
    return;
  }
  location.hash = '#/';
}

// Go to the start page and re-route even if we are already on it.
function goHome() {
  if ((location.hash || '#/') === '#/') route();
  else location.hash = '#/';
}

window.addEventListener('hashchange', route);
route();
