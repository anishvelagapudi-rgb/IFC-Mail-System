import { h, badge, fmtDateTime, emptyState } from '../dom.js';
import { threadList, composer } from './shared.js';
import * as store from '../store.js';

// Staff inbox: one conversation per member (general messages + messages about their mail).
export function messagesView() {
  const root = h('section', { class: 'view' });

  (async () => {
    const [messages, members] = await Promise.all([store.listAllMessages(), store.listMembers()]);
    const byMember = new Map();
    for (const m of messages) {
      if (!byMember.has(m.memberId)) byMember.set(m.memberId, []);
      byMember.get(m.memberId).push(m);
    }
    const convos = [...byMember]
      .map(([memberId, list]) => ({ member: members.find((x) => x.id === memberId), last: list.at(-1), unread: list.filter((x) => !x.seenByStaff).length }))
      .filter((c) => c.member)
      .sort((a, b) => b.unread - a.unread || b.last.at.localeCompare(a.last.at));
    const noConvo = members.filter((m) => !byMember.has(m.id));

    const start = h('select', { 'aria-label': 'Member to message' }, h('option', { value: '' }, 'Start a conversation with…'), noConvo.map((m) => h('option', { value: m.id }, m.name)));
    start.addEventListener('change', () => start.value && (location.hash = `#/messages/${start.value}`));

    root.replaceChildren(
      h('header', { class: 'page-head' }, h('h1', null, 'Messages'), noConvo.length ? start : null),
      convos.length
        ? h(
            'ul',
            { class: 'mail-list' },
            convos.map((c) =>
              h(
                'li',
                null,
                h(
                  'a',
                  { class: 'mail-row', href: `#/messages/${c.member.id}` },
                  h('div', { class: 'grow' }, h('div', { class: 'title' }, c.member.name), h('div', { class: 'hint clip' }, `${c.last.from === 'staff' ? 'You: ' : ''}${c.last.body}`), h('div', { class: 'hint' }, fmtDateTime(c.last.at))),
                  h('div', { class: 'badges' }, c.unread ? badge(`${c.unread} new`, 'warn') : null),
                ),
              ),
            ),
          )
        : emptyState('No messages yet.'),
    );
  })();

  return root;
}

export function conversationView(memberId, onChange) {
  const root = h('section', { class: 'view' });

  async function render() {
    const [member, messages, mail] = await Promise.all([store.getMember(memberId), store.listMemberMessages(memberId), store.listMail()]);
    if (!member) {
      root.replaceChildren(h('h1', null, 'Member not found'), h('a', { href: '#/messages' }, '← Messages'));
      return;
    }
    await store.markSeen('staff', memberId);
    onChange?.();
    const byId = new Map(mail.map((m) => [m.id, m]));
    const mailLabel = (mid) => h('a', { href: `#/mail/${mid}` }, `re: ${byId.get(mid)?.sender.organization || byId.get(mid)?.sender.name || 'mail item'}`);
    root.replaceChildren(
      h('a', { href: '#/messages', class: 'back' }, '← Messages'),
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, member.name), h('p', { class: 'hint' }, [member.phone, member.email].filter(Boolean).join(' · ') || 'No contact details')), h('a', { class: 'btn', href: `#/members/${member.id}` }, 'View profile')),
      h(
        'div',
        { class: 'card' },
        threadList(messages, { me: 'staff', names: { staff: 'Staff', member: member.name, system: 'Update' }, mailLabel }),
        composer({ placeholder: `Message ${member.name}…`, onSend: async (body) => (await store.addMessage({ memberId, from: 'staff', body }), render()) }),
      ),
    );
  }

  render();
  return root;
}
