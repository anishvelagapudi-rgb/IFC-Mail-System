import { h } from '../../dom.js';
import { threadList, composer } from '../shared.js';
import * as store from '../../store.js';
import * as auth from '../../auth.js';

// The member's whole conversation with staff: general messages plus ones about specific mail.
export function memberMessagesView(onChange) {
  const root = h('section', { class: 'view' });

  async function render() {
    const me = auth.current();
    const [messages, mail] = await Promise.all([store.listMemberMessages(me.memberId), store.listMailForMember(me.memberId)]);
    await store.markSeen('member', me.memberId);
    onChange?.();
    const byId = new Map(mail.map((m) => [m.id, m]));
    const mailLabel = (mid) => {
      const m = byId.get(mid);
      return m ? h('a', { href: `#/mail/${mid}` }, `about mail from ${m.sender.organization || m.sender.name || 'unknown sender'}`) : 'about a mail item';
    };
    root.replaceChildren(
      h('h1', null, `Messages with ${me.orgName} staff`),
      h(
        'div',
        { class: 'card' },
        threadList(messages, { me: 'member', names: { staff: 'Staff', member: 'You', system: 'Update' }, mailLabel }),
        composer({ placeholder: 'Write to staff…', onSend: async (body) => (await store.addMessage({ memberId: me.memberId, from: 'member', body }), render()) }),
      ),
      h('p', { class: 'hint' }, 'To ask about one specific item, open it from My mail and message from there.'),
    );
  }

  render();
  return root;
}
