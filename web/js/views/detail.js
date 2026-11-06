import { h, badge, toast, fmtDateTime, fmtDay, daysUntil, toLocalInput, fromLocalInput, emptyState } from '../dom.js';
import { SENDER_TYPES, discardAfter, isTimeSensitive, baseDays } from '../retention.js';
import { toJpeg } from '../camera.js';
import * as store from '../store.js';
import { REQUEST_LABEL, OUTCOME_LABEL, describeRequest, forwardTarget, statusKind } from '../requests-format.js';
import { threadList, composer, zoom } from './shared.js';

export function detailView(id) {
  const root = h('section', { class: 'view' });

  async function render() {
    const mail = await store.getMail(id);
    if (!mail) {
      root.replaceChildren(h('h1', null, 'Mail not found'), h('a', { href: '#/' }, '← Back to inbox'));
      return;
    }
    const [settings, members, requests, messages, notifications] = await Promise.all([
      store.getSettings(),
      store.listMembers(),
      store.listRequests().then((r) => r.filter((x) => x.mailId === id)),
      store.listMessages(id),
      store.listNotifications(id),
    ]);
    const member = members.find((m) => m.id === mail.recipient.memberId) || null;
    const closed = mail.status === 'closed';

    root.replaceChildren(
      h('a', { href: '#/', class: 'back' }, '← Inbox'),
      header(mail, settings),
      h(
        'div',
        { class: 'cols' },
        h('div', null, imagesCard(mail)),
        h('div', null, detailsForm(mail, members, settings, closed), actionsCard(mail, member, closed, requests)),
      ),
      requestsCard(mail, requests, member, closed),
      messagesCard(mail, messages, member),
      notificationsCard(notifications, members),
    );
    if (member) store.markSeen('staff', member.id, id);
  }

  // ---------- header ----------
  function header(mail, settings) {
    const due = discardAfter(mail, settings);
    const badges = [];
    if (mail.status === 'needs_review') badges.push(badge('Needs review', 'warn'));
    if (mail.status === 'ready') badges.push(badge('Ready for pickup', 'ok'));
    if (mail.status === 'closed') badges.push(badge(OUTCOME_LABEL[mail.outcome], 'muted'));
    if (mail.legibility === 'illegible') badges.push(badge('Illegible — flagged', 'err'));
    if (mail.legibility === 'degraded') badges.push(badge('Hard to read', 'warn'));
    if (isTimeSensitive(mail)) badges.push(badge('Time sensitive', 'err'));
    return h(
      'header',
      { class: 'page-head' },
      h('div', null, h('h1', null, mail.sender.organization || mail.sender.name || 'Unknown sender'), h('p', { class: 'hint' }, `Received ${fmtDateTime(mail.receivedAt)}`)),
      h('div', { class: 'badges' }, badges, mail.status !== 'closed' ? badge(daysUntil(due) <= 0 ? 'Eligible to discard' : `Discard after ${fmtDay(due)}`, daysUntil(due) <= 0 ? 'err' : 'muted') : null),
    );
  }

  // ---------- images ----------
  function imagesCard(mail) {
    const img = (imageId, label) => {
      const el = h('img', { alt: `${label} of envelope`, class: 'envelope-img' });
      store.getImageUrl(imageId).then((u) => u && (el.src = u));
      return h('figure', null, imageId ? h('button', { class: 'plain', type: 'button', onclick: () => zoom(el.src) }, el) : h('div', { class: 'gone' }, 'Photo deleted'), h('figcaption', null, label));
    };
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Original photos'),
      h('div', { class: 'pair' }, img(mail.frontImageId, 'Front'), img(mail.backImageId, 'Back')),
      mail.scanImageIds.length ? h('h3', null, 'Scans for member') : null,
      mail.scanImageIds.length ? h('div', { class: 'pair' }, mail.scanImageIds.map((sid, i) => img(sid, `Scan ${i + 1}`))) : null,
    );
  }

  // ---------- details / review form ----------
  function detailsForm(mail, members, settings, closed) {
    const f = {};
    const field = (label, input, hint) => h('label', { class: 'field' }, h('span', null, label), input, hint ? h('small', null, hint) : null);
    const dis = closed ? true : false;

    f.org = h('input', { value: mail.sender.organization, disabled: dis });
    f.sname = h('input', { value: mail.sender.name, disabled: dis });
    f.type = h('select', { value: mail.sender.type || 'unknown', disabled: dis }, SENDER_TYPES.map((t) => h('option', { value: t }, t)));
    f.rname = h('input', { value: mail.recipient.name, disabled: dis, placeholder: 'As written on the envelope' });
    f.member = h(
      'select',
      { value: mail.recipient.memberId || '', disabled: dis },
      h('option', { value: '' }, '— not matched to a member —'),
      members.map((m) => h('option', { value: m.id }, m.name)),
    );
    f.notes = h('textarea', { rows: 3, disabled: dis, placeholder: 'One per line, e.g. Time Sensitive' }, '');
    f.notes.value = mail.notes.join('\n');
    f.legib = h('select', { value: mail.legibility || '', disabled: dis }, [
      h('option', { value: '' }, '— not assessed —'),
      h('option', { value: 'clear' }, 'Clear'),
      h('option', { value: 'degraded' }, 'Hard to read'),
      h('option', { value: 'illegible' }, 'Illegible (flag for in-person help)'),
    ]);
    f.at = h('input', { type: 'datetime-local', value: toLocalInput(mail.receivedAt), disabled: dis });

    // Auto-match the member when staff edit the recipient name and nothing is selected yet.
    f.rname.addEventListener('change', () => {
      if (f.member.value) return;
      const m = store.matchMember(f.rname.value, members);
      if (m) f.member.value = m.id;
    });

    const collect = () => {
      mail.sender = { name: f.sname.value.trim(), organization: f.org.value.trim(), type: f.type.value };
      mail.recipient = { name: f.rname.value.trim(), memberId: f.member.value || null };
      mail.notes = f.notes.value.split('\n').map((s) => s.trim()).filter(Boolean);
      mail.legibility = f.legib.value || null;
      mail.receivedAt = f.at.value ? fromLocalInput(f.at.value) : mail.receivedAt;
    };

    const save = async (confirm) => {
      collect();
      if (confirm && !mail.recipient.name && !mail.recipient.memberId) {
        toast('Enter the recipient (or leave flagged and save as draft).', 'warn');
        return;
      }
      if (confirm) await store.confirmMail(mail);
      else await store.saveMail(mail);
      toast(confirm ? (mail.recipient.memberId ? 'Confirmed. Member notification queued.' : 'Confirmed. No member matched, so no notification sent.') : 'Saved.');
      render();
    };

    const src = mail.processing?.source === 'pipeline' ? 'Read automatically — please verify.' : 'Not read automatically — enter details from the photos.';

    return h(
      'form',
      { class: 'card', onsubmit: (e) => e.preventDefault() },
      h('h2', null, 'Extracted details'),
      closed ? null : h('p', { class: 'hint' }, src + (mail.processing?.error ? ` (${mail.processing.error})` : '')),
      field('Sender (organization)', f.org),
      field('Sender (person, if any)', f.sname),
      field('Sender type', f.type, `Sets the hold period (${baseDays({ sender: { type: f.type.value } }, settings)} days by default).`),
      field('Intended recipient', f.rname),
      field('Member account', f.member, 'The member who gets the notification.'),
      field('Notes on the envelope', f.notes),
      field('Legibility', f.legib),
      field('Time received', f.at),
      closed
        ? null
        : h(
            'div',
            { class: 'row' },
            h('button', { class: 'btn', type: 'button', onclick: () => save(false) }, 'Save draft'),
            mail.status === 'needs_review'
              ? h('button', { class: 'btn primary', type: 'button', onclick: () => save(true) }, 'Confirm & notify member')
              : h('button', { class: 'btn primary', type: 'button', onclick: () => save(false) }, 'Save changes'),
          ),
    );
  }

  // ---------- close-out actions ----------
  function actionsCard(mail, member, closed, requests) {
    if (closed) {
      return h('div', { class: 'card' }, h('h2', null, 'Closed'), h('p', null, `${OUTCOME_LABEL[mail.outcome]} on ${fmtDateTime(mail.closedAt)}.`), mail.redirectedTo ? h('p', null, `Forwarded to ${mail.redirectedTo}.`) : null);
    }
    const act = (label, cls, fn) => h('button', { class: `btn ${cls}`, type: 'button', onclick: fn }, label);
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Close out'),
      h(
        'div',
        { class: 'row wrap' },
        act('Mark picked up', '', async () => {
          await store.closeMail(id, 'picked_up');
          toast('Marked as picked up.');
          render();
        }),
        act('Mark forwarded…', '', async () => {
          const fwd = requests.find((r) => r.type === 'redirect' && r.status === 'approved');
          const suggestion = fwd ? `${forwardTarget(fwd.payload)}${fwd.payload.address ? `, ${fwd.payload.address}` : ''}` : '';
          const to = prompt(`Who was this mail handed or sent to?${member?.trustedContacts?.length ? '\nTrusted people: ' + member.trustedContacts.map((c) => c.name).join('; ') : ''}`, suggestion);
          if (!to) return;
          await store.closeMail(id, 'redirected', { redirectedTo: to.trim() });
          if (fwd) await store.resolveRequest(fwd, 'fulfilled', `Staff forwarded this mail to ${to.trim()}.`);
          toast('Marked as forwarded.');
          render();
        }),
        act('Discard…', 'danger', async () => {
          const settings = await store.getSettings();
          const due = discardAfter(mail, settings);
          const early = daysUntil(due) > 0 ? `\n\nThis is ${daysUntil(due)} day(s) BEFORE the hold period ends (${fmtDay(due)}).` : '';
          if (!confirm(`Discard this mail? The photos will be permanently deleted.${early}`)) return;
          await store.closeMail(id, 'discarded');
          toast('Discarded. Photos deleted.');
          render();
        }),
      ),
    );
  }

  // ---------- member requests ----------
  function requestsCard(mail, requests, member, closed) {
    const rows = requests.map((r) => {
      const detail = describeRequest(r);
      const actions = [];
      if (r.status === 'open' && !closed) {
        const decline = h('button', { class: 'btn', type: 'button', onclick: async () => (await store.resolveRequest(r, 'declined', `Staff declined: ${REQUEST_LABEL[r.type].toLowerCase()}.`), render()) }, 'Decline');
        if (r.type === 'extra_time') {
          const days = h('input', { type: 'number', min: 1, max: 90, value: r.payload.days, class: 'tiny', 'aria-label': 'Days to grant' });
          actions.push(
            days,
            h('button', { class: 'btn primary', type: 'button', onclick: async () => {
              const n = Math.max(1, Number(days.value) || 1);
              mail.extraDays = (mail.extraDays || 0) + n;
              await store.saveMail(mail);
              await store.resolveRequest(r, 'approved', `Staff approved ${n} extra day(s). New hold date: ${fmtDay(discardAfter(mail, await store.getSettings()))}.`);
              render();
            } }, 'Approve'),
            decline,
          );
        } else if (r.type === 'scan') {
          const file = h('input', { type: 'file', accept: 'image/*', hidden: true, onchange: async (e) => {
            const f = e.target.files[0];
            if (!f) return;
            const bmp = await createImageBitmap(f);
            const blob = await toJpeg(bmp, bmp.width, bmp.height);
            mail.scanImageIds.push(await store.addImage(blob, 'scan'));
            await store.saveMail(mail);
            await store.resolveRequest(r, 'fulfilled', 'Staff added a photo of the contents. You can see it on this mail item.');
            render();
          } });
          actions.push(file, h('button', { class: 'btn primary', type: 'button', onclick: () => file.click() }, 'Upload photo of contents…'), decline);
        } else {
          actions.push(
            h('button', { class: 'btn primary', type: 'button', onclick: async () => (await store.resolveRequest(r, 'approved', `Staff approved forwarding this mail to ${forwardTarget(r.payload)}. You will get an update when it is sent.`), render()) }, 'Approve'),
            decline,
          );
        }
      }
      return h('li', { class: 'req' }, h('div', null, h('strong', null, REQUEST_LABEL[r.type]), ' ', badge(r.status, statusKind(r.status)), h('div', { class: 'hint' }, `${detail} · ${fmtDateTime(r.createdAt)}`)), h('div', { class: 'row' }, actions));
    });
    return h('div', { class: 'card' }, h('h2', null, 'Member requests'), rows.length ? h('ul', { class: 'plain-list' }, rows) : emptyState(member ? 'No requests from this member.' : 'Match a member account to receive requests.'));
  }

  // ---------- messaging ----------
  function messagesCard(mail, messages, member) {
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Messages about this item'),
      threadList(messages, { me: 'staff', names: { staff: 'Staff', member: member?.name || 'Member', system: 'Update' } }),
      composer({
        placeholder: member ? `Message ${member.name}…` : 'Match a member account to message them',
        disabled: !member,
        onSend: async (body) => (await store.addMessage({ memberId: member.id, mailId: id, from: 'staff', body }), render()),
      }),
      member ? h('p', { class: 'hint' }, h('a', { href: `#/messages/${member.id}` }, `All messages with ${member.name} →`)) : null,
    );
  }

  function notificationsCard(notifications, members) {
    return h(
      'div',
      { class: 'card' },
      h('h2', null, 'Notification log'),
      notifications.length
        ? h('ul', { class: 'plain-list' }, notifications.map((n) => h('li', null, h('div', null, `To ${members.find((m) => m.id === n.memberId)?.name || 'member'} via ${n.channels.join(' + ')} — `, badge(n.status, 'muted')), h('div', { class: 'hint' }, `${n.body} · ${fmtDateTime(n.at)}`))))
        : emptyState('No notification sent yet. One is queued when you confirm a mail item matched to a member.'),
      h('p', { class: 'hint' }, 'Queued = recorded here. Actual in-app/SMS delivery needs the backend.'),
    );
  }

  render();
  return root;
}
