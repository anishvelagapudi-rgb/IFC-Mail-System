import { h, toast, fmtDay } from '../dom.js';
import { SENDER_TYPES } from '../retention.js';
import { loadSampleData } from '../seed.js';
import * as store from '../store.js';
import * as auth from '../auth.js';

export function settingsView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const s = await store.getSettings();
    const me = auth.current();
    const staff = await auth.listStaff();
    const url = h('input', { type: 'url', value: s.pipelineUrl, placeholder: 'https://… (leave empty for manual entry)' });
    const days = Object.fromEntries(SENDER_TYPES.map((t) => [t, h('input', { type: 'number', min: 1, max: 730, value: s.retentionDays[t], class: 'tiny', 'aria-label': `${t} hold days` })]));

    const save = async () => {
      s.pipelineUrl = url.value.trim();
      for (const t of SENDER_TYPES) s.retentionDays[t] = Math.max(1, Number(days[t].value) || s.retentionDays[t]);
      await store.saveSettings(s);
      toast('Settings saved.');
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
        h('h2', null, 'Image-processing endpoint'),
        h('p', { class: 'hint' }, 'Photos are POSTed here as multipart form data (front, back). See js/pipeline.js for the expected JSON reply. Until set, staff enter details by hand.'),
        url,
      ),
      h('div', { class: 'card' }, h('h2', null, 'Hold period by sender type (days)'), h('p', { class: 'hint' }, 'Placeholder values: confirm with IFC.'), h('div', { class: 'grid-days' }, SENDER_TYPES.map((t) => h('label', { class: 'field' }, h('span', null, t), days[t])))),
      h('button', { class: 'btn primary', type: 'button', onclick: save }, 'Save settings'),
      h('div', { class: 'spacer' }),
      staffCard,
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Data on this device'),
        h('p', { class: 'hint' }, 'Everything is stored in this browser only (IndexedDB), and the login system is temporary. Never enter real member mail here until a secure backend exists.'),
        h('div', { class: 'row wrap' },
          h('button', { class: 'btn', type: 'button', onclick: async () => { await loadSampleData(); toast('Sample members and mail added.'); } }, 'Add sample data'),
          h('button', { class: 'btn danger', type: 'button', onclick: async () => {
            if (!confirm(`Delete ALL mail, members, member accounts and messages for ${me.orgName}? Staff accounts are kept.`)) return;
            await store.wipeOrgData();
            toast('Organization data deleted.');
            render();
          } }, 'Delete this organization’s data'),
        ),
      ),
    );
  }

  render();
  return root;
}
