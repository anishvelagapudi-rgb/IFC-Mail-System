import { h, badge, toast, fmtDay, daysUntil, emptyState } from '../dom.js';
import { discardAfter, baseDays } from '../retention.js';
import * as store from '../store.js';

// Mail past its sender-specific hold period. Staff review and discard in bulk; nothing is
// ever discarded automatically.
export function discardView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const [mail, members, requests, settings] = await Promise.all([store.listMail(), store.listMembers(), store.listRequests(), store.getSettings()]);
    const openReq = new Set(requests.filter((r) => r.status === 'open').map((r) => r.mailId));
    const active = mail.filter((m) => m.status !== 'closed');
    const withDue = active.map((m) => ({ m, due: discardAfter(m, settings) }));
    const eligible = withDue.filter((x) => daysUntil(x.due) <= 0).sort((a, b) => a.due - b.due);
    const soon = withDue.filter((x) => daysUntil(x.due) > 0 && daysUntil(x.due) <= 7).sort((a, b) => a.due - b.due);
    const checks = new Map();

    const line = ({ m, due }, selectable) => {
      const to = members.find((x) => x.id === m.recipient.memberId)?.name || m.recipient.name || 'unknown recipient';
      const cb = selectable ? h('input', { type: 'checkbox', 'aria-label': `Select mail for ${to}` }) : null;
      if (cb) checks.set(m.id, cb);
      return h(
        'li',
        { class: 'req' },
        h('label', { class: 'row grow' }, cb, h('div', null, h('a', { href: `#/mail/${m.id}` }, m.sender.organization || m.sender.name || 'Unknown sender'), h('div', { class: 'hint' }, `To ${to} · ${m.sender.type || 'unknown'} mail, ${baseDays(m, settings) + (m.extraDays || 0)}-day hold · ${selectable ? `eligible since ${fmtDay(due)}` : `eligible ${fmtDay(due)}`}`))),
        openReq.has(m.id) ? badge('Open request', 'warn') : null,
      );
    };

    const discardBtn = h('button', { class: 'btn danger', type: 'button', disabled: !eligible.length }, 'Discard selected…');
    discardBtn.addEventListener('click', async () => {
      const ids = [...checks].filter(([, cb]) => cb.checked).map(([id]) => id);
      if (!ids.length) return toast('Select at least one item.', 'warn');
      const flagged = ids.filter((id) => openReq.has(id)).length;
      const msg = `Discard ${ids.length} item(s)? Photos are permanently deleted.${flagged ? `\n\n${flagged} of them have an open member request.` : ''}`;
      if (!confirm(msg)) return;
      for (const id of ids) await store.closeMail(id, 'discarded');
      toast(`Discarded ${ids.length} item(s).`);
      render();
    });
    const selectAll = h('button', { class: 'btn', type: 'button', onclick: () => {
      const on = [...checks.values()].some((c) => !c.checked);
      checks.forEach((c) => (c.checked = on));
    } }, 'Select all');

    root.replaceChildren(
      h('h1', null, 'Discard queue'),
      h('p', { class: 'hint' }, 'Hold periods depend on sender type and can be edited in Settings. Approved “extra time” requests extend them.'),
      h('div', { class: 'card' }, h('div', { class: 'page-head' }, h('h2', null, `Eligible to discard (${eligible.length})`), h('div', { class: 'row' }, selectAll, discardBtn)), eligible.length ? h('ul', { class: 'plain-list' }, eligible.map((x) => line(x, true))) : emptyState('Nothing is past its hold period.')),
      h('div', { class: 'card' }, h('h2', null, `Coming up in the next 7 days (${soon.length})`), soon.length ? h('ul', { class: 'plain-list' }, soon.map((x) => line(x, false))) : emptyState('Nothing coming up.')),
    );
  }

  render();
  return root;
}
