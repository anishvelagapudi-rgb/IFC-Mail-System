import { h, toast, emptyState } from '../../dom.js';
import * as store from '../../store.js';
import * as auth from '../../auth.js';

const field = (label, input, hint) => h('label', { class: 'field' }, h('span', null, label), input, hint ? h('small', null, hint) : null);

export function memberProfileView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const me = auth.current();
    const m = await store.getMember(me.memberId);

    const name = h('input', { value: m.name, required: true });
    const aliases = h('input', { value: (m.aliases || []).join(', ') });
    const phone = h('input', { type: 'tel', value: m.phone || '' });
    const email = h('input', { type: 'email', value: m.email || '' });
    const info = h(
      'form',
      { class: 'card', onsubmit: async (e) => {
        e.preventDefault();
        await store.saveMember({ ...m, name: name.value.trim(), aliases: aliases.value.split(',').map((s) => s.trim()).filter(Boolean), phone: phone.value.trim(), email: email.value.trim() });
        toast('Saved.');
        render();
      } },
      h('h2', null, 'My information'),
      h('p', { class: 'hint' }, `Staff at ${me.orgName} can see this. Username: ${me.username}`),
      field('Full name', name),
      field('Other names on my mail', aliases, 'Comma-separated.'),
      field('Mobile phone', phone, 'For text alerts.'),
      field('Email', email),
      h('button', { class: 'btn primary', type: 'submit' }, 'Save'),
    );

    const cn = h('textarea', { rows: 2, required: true, placeholder: 'One name per line' });
    const cr = h('input', { placeholder: 'e.g. sister, case manager' });
    const cp = h('input', { type: 'tel' });
    const ca = h('textarea', { rows: 2, placeholder: 'Street, city, state, ZIP' });
    const trusted = h(
      'div',
      { class: 'card' },
      h('h2', null, 'Trusted people'),
      h('p', { class: 'hint' }, 'People you allow to receive your mail. You choose one when you ask staff to forward something.'),
      m.trustedContacts.length
        ? h(
            'ul',
            { class: 'plain-list' },
            m.trustedContacts.map((c) =>
              h(
                'li',
                { class: 'req' },
                h('div', null, h('strong', null, c.name), c.relationship ? ` — ${c.relationship}` : '', h('div', { class: 'hint' }, [c.phone, c.address].filter(Boolean).join(' · ') || 'No phone or address')),
                h('button', { class: 'btn', type: 'button', onclick: async () => {
                  if (!confirm(`Remove ${c.name} from your trusted people?`)) return;
                  m.trustedContacts = m.trustedContacts.filter((x) => x.id !== c.id);
                  await store.saveMember(m);
                  render();
                } }, 'Remove'),
              ),
            ),
          )
        : emptyState('None yet.'),
      h(
        'form',
        { onsubmit: async (e) => {
          e.preventDefault();
          const names = cn.value.split('\n').map((s) => s.trim()).filter(Boolean);
          if (!names.length) return;
          m.trustedContacts.push({ id: store.newId(), name: names.join(', '), relationship: cr.value.trim(), phone: cp.value.trim(), address: ca.value.trim() });
          await store.saveMember(m);
          toast('Trusted person added.');
          render();
        } },
        h('h3', null, 'Add someone'),
        field('Name(s)', cn),
        field('Relationship', cr),
        field('Phone (optional)', cp),
        field('Forwarding address (optional)', ca),
        h('button', { class: 'btn', type: 'submit' }, 'Add'),
      ),
    );

    const oldPw = h('input', { type: 'password', autocomplete: 'current-password', required: true });
    const newPw = h('input', { type: 'password', autocomplete: 'new-password', required: true });
    const pw = h(
      'form',
      { class: 'card', onsubmit: async (e) => {
        e.preventDefault();
        try {
          await auth.changePassword(oldPw.value, newPw.value);
          toast('Password changed.');
          oldPw.value = newPw.value = '';
        } catch (err) {
          toast(err.message, 'err');
        }
      } },
      h('h2', null, 'Change password'),
      field('Current password', oldPw),
      field('New password', newPw, `At least ${auth.MIN_PASSWORD} characters.`),
      h('button', { class: 'btn', type: 'submit' }, 'Change password'),
    );

    root.replaceChildren(h('h1', null, 'My account'), h('div', { class: 'cols' }, h('div', null, info, pw), h('div', null, trusted)));
  }

  render();
  return root;
}
