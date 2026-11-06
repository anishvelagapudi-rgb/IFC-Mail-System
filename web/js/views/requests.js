import { h, badge, fmtDateTime, emptyState } from '../dom.js';
import * as store from '../store.js';

const LABEL = { extra_time: 'Extra time', scan: 'Scanned copy', redirect: 'Redirect' };

// Cross-mail queue of open member requests. Each item links to the mail page to act on it.
export function requestsView() {
  const root = h('section', { class: 'view' }, h('h1', null, 'Member requests'));
  (async () => {
    const [requests, mail, members] = await Promise.all([store.listRequests(), store.listMail(), store.listMembers()]);
    const byId = new Map(mail.map((m) => [m.id, m]));
    const open = requests.filter((r) => r.status === 'open' && byId.get(r.mailId)?.status !== 'closed');
    root.append(
      open.length
        ? h(
            'ul',
            { class: 'plain-list card' },
            open.map((r) => {
              const m = byId.get(r.mailId);
              const who = members.find((x) => x.id === r.memberId)?.name || 'Unknown member';
              return h('li', { class: 'req' }, h('div', null, h('strong', null, `${LABEL[r.type]} — ${who}`), h('div', { class: 'hint' }, `Mail from ${m?.sender.organization || m?.sender.name || 'unknown sender'} · requested ${fmtDateTime(r.createdAt)}`)), h('div', { class: 'row' }, badge('open', 'warn'), h('a', { class: 'btn primary', href: `#/mail/${r.mailId}` }, 'Review')));
            }),
          )
        : emptyState('No open requests.'),
    );
  })();
  return root;
}
