import { h, badge, toast, fmtDateTime, fmtDay, daysUntil, emptyState } from '../../dom.js';
import { discardAfter, isTimeSensitive } from '../../retention.js';
import { REQUEST_LABEL, OUTCOME_LABEL, describeRequest, statusKind } from '../../requests-format.js';
import { threadList, composer, zoomable } from '../shared.js';
import * as store from '../../store.js';
import * as auth from '../../auth.js';

const field = (label, input, hint) => h('label', { class: 'field' }, h('span', null, label), input, hint ? h('small', null, hint) : null);

export function memberMailDetailView(id) {
  const root = h('section', { class: 'view' });

  async function render() {
    const me = auth.current();
    const mail = await store.getMail(id);
    // Members only ever see confirmed mail addressed to them.
    if (!mail || mail.recipient.memberId !== me.memberId || mail.status === 'needs_review') {
      root.replaceChildren(h('h1', null, 'Mail not found'), h('a', { href: '#/' }, '← My mail'));
      return;
    }
    const [settings, member, requests, messages] = await Promise.all([
      store.getSettings(),
      store.getMember(me.memberId),
      store.listRequests().then((r) => r.filter((x) => x.mailId === id)),
      store.listMessages(id),
    ]);
    await store.markSeen('member', me.memberId, id);
    const closed = mail.status === 'closed';
    const due = discardAfter(mail, settings);

    root.replaceChildren(
      h('a', { href: '#/', class: 'back' }, '← My mail'),
      h(
        'header',
        { class: 'page-head' },
        h('div', null, h('h1', null, mail.sender.organization || mail.sender.name || 'Unknown sender'), h('p', { class: 'hint' }, `Arrived ${fmtDateTime(mail.receivedAt)}`)),
        h(
          'div',
          { class: 'badges' },
          isTimeSensitive(mail) ? badge('Time sensitive', 'err') : null,
          closed ? badge(`${OUTCOME_LABEL[mail.outcome]} ${fmtDay(mail.closedAt)}`, 'muted') : badge(`Held until ${fmtDay(due)}`, daysUntil(due) <= 3 ? 'err' : 'muted'),
        ),
      ),
      h(
        'div',
        { class: 'cols' },
        h('div', null, photosCard(mail)),
        h('div', null, closed ? closedCard(mail) : requestForm(mail, member, requests, due), historyCard(requests)),
      ),
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Messages about this mail'),
        threadList(messages, { me: 'member', names: { staff: 'Staff', member: 'You', system: 'Update' } }),
        composer({ placeholder: 'Ask staff about this item…', onSend: async (body) => (await store.addMessage({ memberId: me.memberId, mailId: id, from: 'member', body }), render()) }),
      ),
    );
  }

  function photosCard(mail) {
    const pics = [
      [mail.frontImageId, 'Front of envelope'],
      [mail.backImageId, 'Back of envelope'],
      ...mail.scanImageIds.map((sid, i) => [sid, `Contents, page ${i + 1}`]),
    ];
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Photos'),
      mail.frontImageId || mail.backImageId ? null : h('p', { class: 'hint' }, 'Photos were deleted when this item was closed.'),
      h('div', { class: 'pair' }, pics.filter(([pid]) => pid).map(([pid, label]) => zoomable(pid, label))),
    );
  }

  function closedCard(mail) {
    return h('div', { class: 'card' }, h('h2', null, OUTCOME_LABEL[mail.outcome]), h('p', null, `This item was closed on ${fmtDateTime(mail.closedAt)}.`), mail.redirectedTo ? h('p', null, `Forwarded to ${mail.redirectedTo}.`) : null);
  }

  // One form, any combination of: extra time, photo of contents, forward.
  function requestForm(mail, member, requests, due) {
    const open = new Set(requests.filter((r) => r.status === 'open').map((r) => r.type));
    const check = (type) => h('input', { type: 'checkbox', disabled: open.has(type) });
    const pending = (type) => (open.has(type) ? h('small', null, ' (already requested, waiting on staff)') : null);

    const wantTime = check('extra_time');
    const days = h('select', null, [3, 7, 14, 30].map((d) => h('option', { value: d }, `${d} more days`)));

    const wantScan = check('scan');

    const wantFwd = check('redirect');
    const contacts = member.trustedContacts || [];
    const who = h('select', null, contacts.map((c) => h('option', { value: c.id }, `${c.name}${c.relationship ? ` (${c.relationship})` : ''}`)), h('option', { value: 'new' }, 'Someone new…'));
    const proxyNames = h('textarea', { rows: 2, placeholder: 'One name per line' });
    const relationship = h('input', { placeholder: 'e.g. sister, case manager' });
    const phone = h('input', { type: 'tel' });
    const address = h('textarea', { rows: 3, placeholder: 'Street, city, state, ZIP' });
    const remember = h('input', { type: 'checkbox', checked: true });
    const fill = () => {
      const c = contacts.find((x) => x.id === who.value);
      proxyNames.value = c ? c.name.split(/\s*,\s*/).join('\n') : '';
      relationship.value = c?.relationship || '';
      phone.value = c?.phone || '';
      address.value = c?.address || '';
      rememberRow.hidden = !!c;
    };
    who.addEventListener('change', fill);
    const rememberRow = h('label', { class: 'row' }, remember, h('span', null, 'Save to my trusted people'));
    const fwdFields = h(
      'div',
      { class: 'sub', hidden: true },
      contacts.length ? field('Who should get it?', who) : null,
      field('Name(s) of the people who may receive it', proxyNames, 'Everyone listed is allowed to receive this mail for you.'),
      field('Relationship to you', relationship),
      field('Their phone (optional)', phone),
      field('Address to forward to', address, 'Leave empty if they will pick it up in person.'),
      rememberRow,
    );
    wantFwd.addEventListener('change', () => (fwdFields.hidden = !wantFwd.checked));
    const timeRow = h('div', { class: 'sub', hidden: true }, field('How much longer?', days, `Currently held until ${fmtDay(due)}.`));
    wantTime.addEventListener('change', () => (timeRow.hidden = !wantTime.checked));
    fill();

    const note = h('textarea', { rows: 2, placeholder: 'Anything staff should know (optional)' });

    const submit = async (e) => {
      e.preventDefault();
      const me = auth.current();
      if (!wantTime.checked && !wantScan.checked && !wantFwd.checked) return toast('Choose at least one request.', 'warn');
      let fwd = null;
      if (wantFwd.checked) {
        const names = proxyNames.value.split('\n').map((s) => s.trim()).filter(Boolean);
        if (!names.length) return toast('Enter at least one name to forward to.', 'warn');
        fwd = { proxyNames: names, relationship: relationship.value.trim(), phone: phone.value.trim(), address: address.value.trim(), contactId: who.value !== 'new' ? who.value || null : null };
        if (!contacts.length) fwd.contactId = null;
        if (!fwd.contactId && remember.checked) {
          const c = { id: store.newId(), name: names.join(', '), relationship: fwd.relationship, phone: fwd.phone, address: fwd.address };
          member.trustedContacts = [...contacts, c];
          await store.saveMember(member);
          fwd.contactId = c.id;
        }
      }
      const made = [];
      if (wantTime.checked) made.push(await store.createRequest(mail, 'extra_time', { days: Number(days.value) }));
      if (wantScan.checked) made.push(await store.createRequest(mail, 'scan', {}));
      if (fwd) made.push(await store.createRequest(mail, 'redirect', fwd));
      if (note.value.trim()) await store.addMessage({ memberId: me.memberId, mailId: mail.id, from: 'member', body: note.value.trim() });
      toast(`Sent ${made.length} request${made.length > 1 ? 's' : ''} to staff.`);
      render();
    };

    return h(
      'form',
      { class: 'card', onsubmit: submit },
      h('h2', null, 'Ask staff for help with this mail'),
      h('p', { class: 'hint' }, 'Choose one or more.'),
      h('label', { class: 'row' }, wantTime, h('span', null, h('strong', null, 'More time'), ' before it is thrown away'), pending('extra_time')),
      timeRow,
      h('label', { class: 'row' }, wantScan, h('span', null, h('strong', null, 'A photo of what is inside'), ' (staff open it and photograph the contents)'), pending('scan')),
      h('label', { class: 'row' }, wantFwd, h('span', null, h('strong', null, 'Forward it'), ' to someone I trust'), pending('redirect')),
      fwdFields,
      field('Note', note),
      h('button', { class: 'btn primary', type: 'submit' }, 'Send request'),
    );
  }

  function historyCard(requests) {
    if (!requests.length) return null;
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Your requests'),
      h('ul', { class: 'plain-list' }, requests.map((r) => h('li', null, h('strong', null, REQUEST_LABEL[r.type]), ' ', badge(r.status === 'open' ? 'waiting on staff' : r.status, statusKind(r.status)), h('div', { class: 'hint' }, `${describeRequest(r)} · ${fmtDateTime(r.createdAt)}`)))),
    );
  }

  render();
  return root;
}
