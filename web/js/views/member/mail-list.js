import { h, badge, fmtDateTime, fmtDay, daysUntil, emptyState } from '../../dom.js';
import { discardAfter, isTimeSensitive } from '../../retention.js';
import { OUTCOME_LABEL } from '../../requests-format.js';
import * as store from '../../store.js';
import * as auth from '../../auth.js';

export function memberMailListView() {
  const root = h('section', { class: 'view' });

  (async () => {
    const me = auth.current();
    const [mail, requests, settings] = await Promise.all([store.listMailForMember(me.memberId), store.listRequests(), store.getSettings()]);
    const openReq = new Set(requests.filter((r) => r.status === 'open').map((r) => r.mailId));
    const waiting = mail.filter((m) => m.status !== 'closed');
    const past = mail.filter((m) => m.status === 'closed');

    const row = (m) => {
      const thumb = h('img', { alt: '', class: 'thumb' });
      store.getImageUrl(m.frontImageId).then((u) => u && (thumb.src = u));
      const due = discardAfter(m, settings);
      const flags = [];
      if (isTimeSensitive(m)) flags.push(badge('Time sensitive', 'err'));
      if (openReq.has(m.id)) flags.push(badge('Request pending', 'warn'));
      if (m.scanImageIds.length) flags.push(badge('Photo of contents', 'ok'));
      if (m.status === 'closed') flags.push(badge(OUTCOME_LABEL[m.outcome], 'muted'));
      else flags.push(badge(daysUntil(due) <= 3 ? `Pick up by ${fmtDay(due)}` : `Held until ${fmtDay(due)}`, daysUntil(due) <= 3 ? 'err' : 'muted'));
      return h(
        'li',
        null,
        h(
          'a',
          { class: 'mail-row', href: `#/mail/${m.id}` },
          m.frontImageId ? thumb : h('div', { class: 'thumb gone' }),
          h('div', { class: 'grow' }, h('div', { class: 'title' }, m.sender.organization || m.sender.name || 'Unknown sender'), h('div', { class: 'hint' }, `Arrived ${fmtDateTime(m.receivedAt)}`)),
          h('div', { class: 'badges' }, flags),
        ),
      );
    };

    root.replaceChildren(
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'My mail'), h('p', { class: 'hint' }, `Held for you at ${me.orgName}.`))),
      h('h2', null, `Waiting for you (${waiting.length})`),
      waiting.length ? h('ul', { class: 'mail-list' }, waiting.map(row)) : emptyState('No mail waiting right now. You will be notified when something arrives.'),
      ...(past.length ? [h('h2', null, `Earlier mail (${past.length})`), h('ul', { class: 'mail-list' }, past.map(row))] : []),
    );
  })();

  return root;
}
