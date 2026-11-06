import { h, badge, toast, fmtDateTime, emptyState } from '../dom.js';
import * as store from '../store.js';

const CHANNEL = { sms: 'Text', phone: 'Phone call', in_person: 'In person', other: 'Other' };
const daysAgo = (iso) => Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);

// Urgent mail that is ready but unclaimed past the org's follow-up threshold.
// Staff log each attempt to reach the member. "Send text" is simulated: nothing is sent yet.
export function followupView() {
  const root = h('section', { class: 'view' });

  async function render() {
    let data;
    try {
      data = await store.listFollowups();
    } catch (err) {
      root.replaceChildren(h('h1', null, 'Follow-up'), emptyState(`Could not load: ${err.message}`));
      return;
    }

    const item = ({ mail: m, member, attempts }) => {
      const from = m.sender.organization || m.sender.name || 'Unknown sender';
      const sms = h('textarea', { rows: 2, value: `Hi ${member?.name?.split(' ')[0] || ''}, you have time-sensitive mail from ${from} waiting at the front desk. Please pick it up soon.`, 'aria-label': 'Text message' });
      const channel = h('select', { 'aria-label': 'How you reached out' }, ['phone', 'in_person', 'other'].map((c) => h('option', { value: c }, CHANNEL[c])));
      const outcome = h('input', { placeholder: 'Outcome (e.g. left voicemail, will come Friday)' });
      const run = (fn, msg) => async (e) => {
        e?.preventDefault?.();
        try {
          await fn();
          toast(msg);
          render();
        } catch (err) {
          toast(err.message, 'err');
        }
      };
      return h(
        'div',
        { class: 'card' },
        h(
          'div',
          { class: 'page-head' },
          h('div', null, h('h3', null, h('a', { href: `#/mail/${m.id}` }, from)), h('div', { class: 'hint' }, `For ${member?.name || 'unknown'} · received ${fmtDateTime(m.receivedAt)} (${daysAgo(m.receivedAt)} days ago)`)),
          h('div', { class: 'badges' }, badge('Urgent', 'err'), attempts.length ? badge(`${attempts.length} attempt${attempts.length > 1 ? 's' : ''}`, 'muted') : badge('Not contacted', 'warn')),
        ),
        m.notes.length ? h('p', { class: 'hint' }, `Marked: ${m.notes.join(' · ')}`) : null,
        h('p', null, member?.phone ? `Phone: ${member.phone}` : 'No phone number on file.'),
        h('h4', null, 'Send a text'),
        h('p', { class: 'hint' }, 'Simulated for now: the text is recorded in the follow-up log but not sent.'),
        sms,
        h('div', { class: 'row wrap' }, h('button', { class: 'btn primary', type: 'button', disabled: !member?.phone, onclick: run(() => store.sendFollowupText(m.id, sms.value), 'Text logged (simulated).') }, 'Send text (simulated)')),
        h('h4', null, 'Log another attempt'),
        h('form', { class: 'row wrap', onsubmit: run(() => store.logFollowup(m.id, { channel: channel.value, outcome: outcome.value }), 'Follow-up logged.') }, channel, outcome, h('button', { class: 'btn', type: 'submit' }, 'Log')),
        attempts.length
          ? h(
              'ul',
              { class: 'plain-list' },
              attempts.map((a) => h('li', null, h('strong', null, CHANNEL[a.channel] || a.channel), a.simulated ? ' (simulated)' : '', ` — ${a.outcome || 'no outcome noted'}`, h('div', { class: 'hint' }, fmtDateTime(a.at)))),
            )
          : null,
      );
    };

    root.replaceChildren(
      h('h1', null, `Follow-up (${data.items.length})`),
      h('p', { class: 'hint' }, `Urgent mail ready for pickup and not collected after ${data.afterDays} day(s). Change the threshold in Settings.`),
      ...(data.items.length ? data.items.map(item) : [emptyState('Nothing urgent is waiting. Nice.')]),
    );
  }

  render();
  return root;
}

// Shown to a member whose sign-up is waiting for an admin.
export function pendingView(session, onCheck) {
  const rejected = session.status === 'rejected';
  return h(
    'section',
    { class: 'view auth' },
    h('h1', null, rejected ? 'Account not approved' : 'Waiting for approval'),
    h(
      'div',
      { class: 'card' },
      h('p', null, rejected
        ? `Staff at ${session.orgName} could not approve this account. Please talk to them at the front desk.`
        : `Thanks, ${session.name || session.username}. Staff at ${session.orgName} need to confirm who you are before you can see your mail. This usually happens when you next visit.`),
      rejected ? null : h('button', { class: 'btn primary', type: 'button', onclick: onCheck }, 'Check again'),
    ),
  );
}
