import { h, badge, fmtDateTime, fmtDay, daysUntil, emptyState } from '../dom.js';
import { discardAfter, isTimeSensitive } from '../retention.js';
import * as store from '../store.js';

const FILTERS = [
  ['active', 'All active'],
  ['review', 'Needs review'],
  ['ready', 'Ready for pickup'],
  ['requests', 'Open requests'],
  ['closed', 'Closed'],
];

export function inboxView() {
  const root = h('section', { class: 'view' });
  let filter = 'active';
  let query = '';

  async function render() {
    const [mail, requests, members, settings] = await Promise.all([store.listMail(), store.listRequests(), store.listMembers(), store.getSettings()]);
    const openReq = new Set(requests.filter((r) => r.status === 'open').map((r) => r.mailId));
    const nameOf = (m) => members.find((x) => x.id === m.recipient.memberId)?.name || m.recipient.name || '';

    const tests = {
      active: (m) => m.status !== 'closed',
      review: (m) => m.status === 'needs_review',
      ready: (m) => m.status === 'ready',
      requests: (m) => m.status !== 'closed' && openReq.has(m.id),
      closed: (m) => m.status === 'closed',
    };
    const counts = Object.fromEntries(FILTERS.map(([k]) => [k, mail.filter(tests[k]).length]));
    const q = query.trim().toLowerCase();
    const rows = mail
      .filter(tests[filter])
      .filter((m) => !q || [m.sender.organization, m.sender.name, nameOf(m), ...m.notes].join(' ').toLowerCase().includes(q));

    const tabs = h(
      'div',
      { class: 'tabs', role: 'tablist' },
      FILTERS.map(([k, label]) =>
        h('button', { class: `tab ${k === filter ? 'on' : ''}`, type: 'button', role: 'tab', 'aria-selected': k === filter, onclick: () => ((filter = k), render()) }, label, ' ', h('span', { class: 'count' }, counts[k])),
      ),
    );
    const search = h('input', { type: 'search', placeholder: 'Search sender, recipient, notes…', value: query, 'aria-label': 'Search mail' });
    search.addEventListener('input', () => {
      query = search.value;
      const pos = search.selectionStart;
      render().then(() => {
        const s = root.querySelector('input[type=search]');
        s?.focus();
        s?.setSelectionRange(pos, pos);
      });
    });

    root.replaceChildren(
      h('header', { class: 'page-head' }, h('h1', null, 'Mail inbox'), h('a', { class: 'btn primary', href: '#/capture' }, '＋ Scan new mail')),
      tabs,
      search,
      rows.length
        ? h('ul', { class: 'mail-list' }, rows.map((m) => row(m, nameOf(m), openReq.has(m.id), settings)))
        : emptyState(mail.length ? 'Nothing matches this filter.' : 'No mail yet. Scan the first item, or load sample data in Settings.'),
    );
  }

  function row(m, recipient, hasReq, settings) {
    const thumb = h('img', { alt: '', class: 'thumb' });
    store.getImageUrl(m.frontImageId).then((u) => u && (thumb.src = u));
    const due = discardAfter(m, settings);
    const flags = [];
    if (m.status === 'needs_review') flags.push(badge('Needs review', 'warn'));
    if (m.legibility === 'illegible') flags.push(badge('Illegible', 'err'));
    if (isTimeSensitive(m)) flags.push(badge('Time sensitive', 'err'));
    if (hasReq) flags.push(badge('Request', 'warn'));
    if (m.status === 'closed') flags.push(badge(m.outcome.replace('_', ' '), 'muted'));
    else if (daysUntil(due) <= 0) flags.push(badge('Discardable', 'muted'));
    return h(
      'li',
      null,
      h(
        'a',
        { class: 'mail-row', href: `#/mail/${m.id}` },
        m.frontImageId ? thumb : h('div', { class: 'thumb gone' }),
        h('div', { class: 'grow' }, h('div', { class: 'title' }, m.sender.organization || m.sender.name || 'Unknown sender'), h('div', { class: 'hint' }, `To: ${recipient || 'unknown recipient'}`), h('div', { class: 'hint' }, `Received ${fmtDateTime(m.receivedAt)}${m.status !== 'closed' ? ` · hold until ${fmtDay(due)}` : ''}`)),
        h('div', { class: 'badges' }, flags),
      ),
    );
  }

  render();
  return root;
}
