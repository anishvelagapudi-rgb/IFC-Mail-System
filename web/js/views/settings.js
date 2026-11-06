import { h, toast, fmtDay } from '../dom.js';
import { SENDER_TYPES } from '../retention.js';
import * as store from '../store.js';
import * as auth from '../auth.js';

export function settingsView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const s = await store.getSettings();
    const me = auth.current();
    const staff = await auth.listStaff();
    const fuDays = h('input', { type: 'number', min: 0, max: 90, value: s.followupAfterDays, class: 'tiny', 'aria-label': 'Follow-up after days' });
    const minConf = h('input', { type: 'number', min: 0, max: 1, step: 0.05, value: s.minConfidence, class: 'tiny', 'aria-label': 'Minimum confidence' });
    const days = Object.fromEntries(SENDER_TYPES.map((t) => [t, h('input', { type: 'number', min: 1, max: 730, value: s.retentionDays[t], class: 'tiny', 'aria-label': `${t} hold days` })]));

    const save = async () => {
      s.followupAfterDays = Math.max(0, Number(fuDays.value) || 0);
      s.minConfidence = Math.min(1, Math.max(0, Number(minConf.value) || 0));
      for (const t of SENDER_TYPES) s.retentionDays[t] = Math.max(1, Number(days[t].value) || s.retentionDays[t]);
      try {
        await store.saveSettings(s);
        toast('Settings saved.');
      } catch (err) {
        toast(err.message, 'err');
      }
    };

    const sn = h('input', { placeholder: 'Name', required: true });
    const su = h('input', { placeholder: 'Username', required: true, autocapitalize: 'none' });
    const sp = h('input', { type: 'password', placeholder: 'Temporary password', required: true, autocomplete: 'new-password' });
    const staffCard = h(
      'div',
      { class: 'card' },
      h('h2', null, 'Staff accounts'),
      h('ul', { class: 'plain-list' }, staff.map((u) => h('li', null, h('strong', null, u.name || u.username), ` — ${u.username}`, u.id === me.userId ? ' (you)' : '', h('div', { class: 'hint' }, `Added ${fmtDay(u.createdAt)}`)))),
      h(
        'form',
        { class: 'row wrap', onsubmit: async (e) => {
          e.preventDefault();
          try {
            await auth.createUser({ username: su.value, password: sp.value, role: 'admin', orgId: me.orgId, name: sn.value.trim() });
            toast('Staff account created.');
            render();
          } catch (err) {
            toast(err.message, 'err');
          }
        } },
        sn,
        su,
        sp,
        h('button', { class: 'btn', type: 'submit' }, 'Add staff'),
      ),
    );

    root.replaceChildren(
      h('h1', null, 'Settings'),
      h('p', { class: 'hint' }, `Organization: ${me.orgName}`),
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Image processing and follow-up'),
        h('p', { class: 'hint' }, 'Scanned envelopes are read automatically. Below this confidence, an item is flagged illegible for a person to enter instead of guessed.'),
        h('div', { class: 'grid-days' },
          h('label', { class: 'field' }, h('span', null, 'Minimum confidence (0–1)'), minConf),
          h('label', { class: 'field' }, h('span', null, 'Follow up on urgent mail after (days)'), fuDays),
        ),
      ),
      h('div', { class: 'card' }, h('h2', null, 'Hold period by sender type (days)'), h('p', { class: 'hint' }, 'Placeholder values: confirm with IFC.'), h('div', { class: 'grid-days' }, SENDER_TYPES.map((t) => h('label', { class: 'field' }, h('span', null, t), days[t])))),
      h('button', { class: 'btn primary', type: 'button', onclick: save }, 'Save settings'),
      h('div', { class: 'spacer' }),
      staffCard,
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Danger zone'),
        h('p', { class: 'hint' }, 'Permanently deletes this organization’s mail, photos, members, member logins, requests and messages. Staff logins and settings are kept.'),
        h('div', { class: 'row wrap' },
          h('button', { class: 'btn danger', type: 'button', onclick: async () => {
            if (prompt(`Type DELETE to erase all mail, members and member accounts for ${me.orgName}.`) !== 'DELETE') return;
            try {
              await store.wipeOrgData();
              toast('Organization data deleted.');
            } catch (err) {
              toast(err.message, 'err');
            }
            render();
          } }, 'Delete this organization’s data'),
        ),
      ),
    );
  }

  render();
  return root;
}
