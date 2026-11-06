import { h, badge, toast, fmtDay, emptyState } from '../dom.js';
import * as store from '../store.js';
import * as db from '../db.js';

// The org's members: people who registered an account plus anyone staff added by hand
// (so envelope names can still be matched before the person signs up).
export function membersView(focusId) {
  const root = h('section', { class: 'view' });
  let query = '';

  async function render() {
    const [members, mail, users] = await Promise.all([store.listMembers(), store.listMail(), db.getAll('users')]);
    const userOf = (m) => users.find((u) => u.id === m.userId);
    const mailCount = (m) => mail.filter((x) => x.recipient.memberId === m.id && x.status !== 'closed').length;

    const name = h('input', { required: true, placeholder: 'Full name' });
    const aliases = h('input', { placeholder: 'Nicknames / spellings, comma-separated' });
    const phone = h('input', { type: 'tel', placeholder: 'Mobile (for SMS)' });
    const add = h(
      'details',
      { class: 'card' },
      h('summary', null, h('strong', null, 'Add a member by hand')),
      h('p', { class: 'hint' }, 'For people who have not created an account yet. Members can also register themselves.'),
      h(
        'form',
        { class: 'row wrap', onsubmit: async (e) => {
          e.preventDefault();
          await store.saveMember({ name: name.value.trim(), aliases: aliases.value.split(',').map((s) => s.trim()).filter(Boolean), phone: phone.value.trim() });
          toast('Member added.');
          render();
        } },
        name,
        aliases,
        phone,
        h('button', { class: 'btn primary', type: 'submit' }, 'Add'),
      ),
    );

    const card = (m) => {
      const u = userOf(m);
      const cn = h('input', { placeholder: 'Name(s)', required: true });
      const cr = h('input', { placeholder: 'Relationship' });
      const cp = h('input', { type: 'tel', placeholder: 'Phone' });
      const ca = h('input', { placeholder: 'Forwarding address' });
      const n = mailCount(m);
      return h(
        'div',
        { class: `card ${m.id === focusId ? 'focus' : ''}`, id: `member-${m.id}` },
        h(
          'div',
          { class: 'page-head' },
          h('h3', null, m.name),
          h('div', { class: 'badges' }, u ? badge(`Account: ${u.username}`, 'ok') : badge('No account', 'muted'), n ? badge(`${n} item${n > 1 ? 's' : ''} held`, 'warn') : null),
        ),
        h(
          'dl',
          { class: 'facts' },
          h('dt', null, 'Phone'), h('dd', null, m.phone || '—'),
          h('dt', null, 'Email'), h('dd', null, m.email || '—'),
          h('dt', null, 'Other names'), h('dd', null, m.aliases.join(', ') || '—'),
          h('dt', null, 'Registered'), h('dd', null, m.registeredAt ? fmtDay(m.registeredAt) : 'Added by staff'),
        ),
        h('div', { class: 'row wrap' }, h('a', { class: 'btn', href: `#/messages/${m.id}` }, 'Message')),
        h('h4', null, 'Trusted people'),
        m.trustedContacts.length
          ? h('ul', { class: 'plain-list' }, m.trustedContacts.map((c) => h('li', null, h('strong', null, c.name), ` — ${c.relationship || 'contact'}`, h('div', { class: 'hint' }, [c.phone, c.address].filter(Boolean).join(' · ') || 'No phone or address'))))
          : emptyState('None yet.'),
        h(
          'form',
          { class: 'row wrap', onsubmit: async (e) => {
            e.preventDefault();
            m.trustedContacts.push({ id: store.newId(), name: cn.value.trim(), relationship: cr.value.trim(), phone: cp.value.trim(), address: ca.value.trim() });
            await store.saveMember(m);
            render();
          } },
          cn,
          cr,
          cp,
          ca,
          h('button', { class: 'btn', type: 'submit' }, 'Add trusted person'),
        ),
      );
    };

    const q = query.trim().toLowerCase();
    const shown = members.filter((m) => !q || [m.name, ...m.aliases, m.phone, m.email, userOf(m)?.username].join(' ').toLowerCase().includes(q));
    const search = h('input', { type: 'search', placeholder: 'Search name, phone, email, username…', value: query, 'aria-label': 'Search members' });
    search.addEventListener('input', () => {
      query = search.value;
      render().then(() => root.querySelector('input[type=search]')?.focus());
    });

    root.replaceChildren(
      h('h1', null, `Members (${members.length})`),
      h('p', { class: 'hint' }, `${members.filter(userOf).length} registered an account · ${members.filter((m) => !userOf(m)).length} added by staff`),
      add,
      search,
      ...(shown.length ? shown.map(card) : [emptyState(members.length ? 'No one matches.' : 'No members yet.')]),
    );
    if (focusId) root.querySelector(`#member-${CSS.escape(focusId)}`)?.scrollIntoView({ block: 'start' });
  }

  render();
  return root;
}
