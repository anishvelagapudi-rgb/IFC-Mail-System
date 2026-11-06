import { h, toast } from '../dom.js';
import { SENDER_TYPES } from '../retention.js';
import { loadSampleData } from '../seed.js';
import * as store from '../store.js';

export function settingsView() {
  const root = h('section', { class: 'view' });

  async function render() {
    const s = await store.getSettings();
    const url = h('input', { type: 'url', value: s.pipelineUrl, placeholder: 'https://… (leave empty for manual entry)' });
    const demo = h('input', { type: 'checkbox' });
    demo.checked = s.demoTools;
    const days = Object.fromEntries(SENDER_TYPES.map((t) => [t, h('input', { type: 'number', min: 1, max: 730, value: s.retentionDays[t], class: 'tiny', 'aria-label': `${t} hold days` })]));

    const save = async () => {
      s.pipelineUrl = url.value.trim();
      s.demoTools = demo.checked;
      for (const t of SENDER_TYPES) s.retentionDays[t] = Math.max(1, Number(days[t].value) || s.retentionDays[t]);
      await store.saveSettings(s);
      toast('Settings saved.');
    };

    root.replaceChildren(
      h('h1', null, 'Settings'),
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Image-processing endpoint'),
        h('p', { class: 'hint' }, 'Photos are POSTed here as multipart form data (front, back). See js/pipeline.js for the expected JSON reply. Until set, staff enter details by hand.'),
        url,
      ),
      h('div', { class: 'card' }, h('h2', null, 'Hold period by sender type (days)'), h('p', { class: 'hint' }, 'Placeholder values: confirm with IFC.'), h('div', { class: 'grid-days' }, SENDER_TYPES.map((t) => h('label', { class: 'field' }, h('span', null, t), days[t])))),
      h('div', { class: 'card' }, h('label', { class: 'row' }, demo, h('span', null, 'Show demo tools (act as member) on mail pages'))),
      h('button', { class: 'btn primary', type: 'button', onclick: save }, 'Save settings'),
      h(
        'div',
        { class: 'card' },
        h('h2', null, 'Data on this device'),
        h('p', { class: 'hint' }, 'Everything is stored in this browser only (IndexedDB). Never enter real member mail here until a secure backend exists.'),
        h('div', { class: 'row wrap' },
          h('button', { class: 'btn', type: 'button', onclick: async () => { await loadSampleData(); toast('Sample data loaded.'); } }, 'Load sample data'),
          h('button', { class: 'btn danger', type: 'button', onclick: async () => {
            if (!confirm('Delete ALL mail, members, messages and settings stored in this browser?')) return;
            await store.wipeEverything();
            toast('All local data deleted.');
            render();
          } }, 'Delete all local data'),
        ),
      ),
    );
  }

  render();
  return root;
}
