import { h, toast, emptyState } from '../dom.js';
import * as store from '../store.js';

// Local roster used to match envelope names to member accounts. In production this comes from
// IFC's real member/account system, not from here.
export function membersView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const members = await store.listMembers();

    const name = h('input', { required: true, placeholder: 'Full name' });
    const aliases = h('input', { placeholder: 'Nicknames / spellings, comma-separated' });
    const phone = h('input', { type: 'tel', placeholder: 'Mobile (for SMS)' });
    const add = h(
      'form',
      { class: 'card', onsubmit: async (e) => {
        e.preventDefault();
        await store.saveMember({ name: name.value.trim(), aliases: aliases.value.split(',').map((s) => s.trim()).filter(Boolean), phone: phone.value.trim() });
        toast('Member added.');
        render();
      } },
      h('h2', null, 'Add member'),
      h('div', { class: 'row wrap' }, name, aliases, phone, h('button', { class: 'btn primary', type: 'submit' }, 'Add')),
    );

    const card = (m) => {
      const cn = h('input', { placeholder: 'Contact name', required: true });
      const cr = h('input', { placeholder: 'Relationship (e.g. case manager)' });
      const cp = h('input', { type: 'tel', placeholder: 'Phone' });
      return h(
        'div',
        { class: 'card' },
        h('h3', null, m.name),
        h('p', { class: 'hint' }, `${m.phone || 'no phone'} · also known as: ${m.aliases.join(', ') || '—'}`),
        h('h4', null, 'Trusted contacts'),
        m.trustedContacts.length
          ? h('ul', { class: 'plain-list' }, m.trustedContacts.map((c) => h('li', null, `${c.name} — ${c.relationship || 'contact'} ${c.phone || ''}`)))
          : emptyState('None yet.'),
        h(
          'form',
          { class: 'row wrap', onsubmit: async (e) => {
            e.preventDefault();
            m.trustedContacts.push({ id: store.newId(), name: cn.value.trim(), relationship: cr.value.trim(), phone: cp.value.trim() });
            await store.saveMember(m);
            render();
          } },
          cn,
          cr,
          cp,
          h('button', { class: 'btn', type: 'submit' }, 'Add contact'),
        ),
      );
    };

    root.replaceChildren(h('h1', null, 'Members'), add, members.length ? members.map(card) : emptyState('No members yet.'));
  }

  render();
  return root;
}
