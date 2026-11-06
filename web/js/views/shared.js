// UI pieces used by both the staff and member screens.
import { h, fmtDateTime, emptyState } from '../dom.js';
import * as store from '../store.js';

// me: which side is viewing ('staff' | 'member'), so "my" bubbles go on the right.
// names: label per sender. mailLabel(mailId) optionally tags messages about a specific item.
export function threadList(messages, { me, names, mailLabel }) {
  if (!messages.length) return emptyState('No messages yet.');
  return h(
    'ul',
    { class: 'thread' },
    messages.map((m) =>
      h(
        'li',
        { class: `msg ${m.from} ${m.from === me ? 'mine' : ''}` },
        h('div', { class: 'who' }, `${names[m.from]} · ${fmtDateTime(m.at)}`, m.mailId && mailLabel ? h('span', null, ' · ', mailLabel(m.mailId)) : null),
        h('div', null, m.body),
      ),
    ),
  );
}

export function composer({ placeholder, onSend, disabled = false }) {
  const body = h('textarea', { rows: 2, placeholder, disabled, 'aria-label': 'Message' });
  const send = h('button', { class: 'btn primary', type: 'submit', disabled }, 'Send');
  return h(
    'form',
    {
      class: 'composer',
      onsubmit: async (e) => {
        e.preventDefault();
        const text = body.value.trim();
        if (!text) return;
        send.disabled = true;
        await onSend(text);
      },
    },
    body,
    send,
  );
}

export function zoom(src) {
  if (!src) return;
  const dlg = h('dialog', { class: 'zoom', onclick: () => dlg.close(), onclose: () => dlg.remove() }, h('img', { src, alt: 'Enlarged photo' }));
  document.body.append(dlg);
  dlg.showModal();
}

export function zoomable(imageId, label) {
  const el = h('img', { alt: label, class: 'envelope-img' });
  store.getImageUrl(imageId).then((u) => u && (el.src = u));
  return h(
    'figure',
    null,
    imageId ? h('button', { class: 'plain', type: 'button', onclick: () => zoom(el.src), 'aria-label': `Enlarge ${label}` }, el) : h('div', { class: 'gone' }, 'Photo deleted'),
    h('figcaption', null, label),
  );
}
