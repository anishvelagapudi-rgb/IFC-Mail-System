import { h, badge, toast, fmtDay, emptyState } from '../dom.js';
import * as store from '../store.js';

// The org's members: people who registered an account plus anyone staff added by hand
// (so envelope names can still be matched before the person signs up).
export function membersView(focusId) {
  const root = h('section', { class: 'view' });
  let query = '';

  async function render() {
    const [members, mail, users] = await Promise.all([store.listMembers(), store.listMail(), store.listAccounts()]);
    const userOf = (m) => users.find((u) => u.memberId === m.id && u.status === 'active');
    const pending = users.filter((u) => u.role === 'member' && u.status === 'pending');
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
          try {
            await store.saveMember({ name: name.value.trim(), aliases: aliases.value.split(',').map((s) => s.trim()).filter(Boolean), phone: phone.value.trim() });
            toast('Member added.');
          } catch (err) {
            toast(err.message, 'err');
          }
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
            try {
              await store.saveMember(m);
            } catch (err) {
              toast(err.message, 'err');
            }
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

    // Sign-ups wait here until staff confirm who they are. Linking to an existing roster entry
    // gives them the mail already held under that name; otherwise a new entry is created.
    const unlinked = members.filter((m) => !users.some((u) => u.memberId === m.id && u.status === 'active'));
    const approvalCard = (u) => {
      const r = u.registration || {};
      const guess = store.matchMember(r.name, unlinked);
      const pick = h(
        'select',
        { 'aria-label': `Roster entry for ${u.username}`, value: guess ? guess.id : '' },
        h('option', { value: '' }, 'New member from these details'),
        unlinked.map((m) => h('option', { value: m.id }, `Link to ${m.name}${m.aliases.length ? ` (${m.aliases.join(', ')})` : ''}`)),
      );
      const act = (fn, msg) => async () => {
        try {
          await fn();
          toast(msg);
        } catch (err) {
          toast(err.message, 'err');
        }
        render();
      };
      return h(
        'div',
        { class: 'card focus' },
        h('div', { class: 'page-head' }, h('h3', null, r.name || u.name || u.username), h('div', { class: 'badges' }, badge('Waiting for approval', 'warn'))),
        h(
          'dl',
          { class: 'facts' },
          h('dt', null, 'Username'), h('dd', null, u.username),
          h('dt', null, 'Other names'), h('dd', null, (r.aliases || []).join(', ') || '—'),
          h('dt', null, 'Phone'), h('dd', null, r.phone || '—'),
          h('dt', null, 'Email'), h('dd', null, r.email || '—'),
          h('dt', null, 'Signed up'), h('dd', null, fmtDay(u.createdAt)),
        ),
        h('p', { class: 'hint' }, 'Check who this is before approving: once linked, they can see that person’s mail.'),
        h(
          'div',
          { class: 'row wrap' },
          pick,
          h('button', { class: 'btn primary', type: 'button', onclick: act(() => store.approveAccount(u.id, pick.value || null), 'Account approved.') }, 'Approve'),
          h('button', { class: 'btn', type: 'button', onclick: () => confirm(`Reject the sign-up from ${u.username}?`) && act(() => store.rejectAccount(u.id), 'Sign-up rejected.')() }, 'Reject'),
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
      pending.length ? h('h2', null, `Waiting for approval (${pending.length})`) : null,
      ...pending.map(approvalCard),
      add,
      search,
      ...(shown.length ? shown.map(card) : [emptyState(members.length ? 'No one matches.' : 'No members yet.')]),
    );
    if (focusId) root.querySelector(`#member-${CSS.escape(focusId)}`)?.scrollIntoView({ block: 'start' });
  }

  render();
  return root;
}
