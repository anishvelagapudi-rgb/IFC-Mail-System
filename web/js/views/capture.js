import { h, toast } from '../dom.js';
import { captureWidget } from '../camera.js';
import { processEnvelope } from '../pipeline.js';
import * as store from '../store.js';

// Three steps: front -> back -> review photos -> process & save.
export function captureView() {
  const photos = { front: null, back: null };
  const urls = [];
  let widget = null;
  const root = h('section', { class: 'view' });

  const cleanup = () => {
    widget?.stop();
    widget = null;
  };
  root.destroy = () => {
    cleanup();
    urls.forEach(URL.revokeObjectURL);
  };

  const preview = (blob) => {
    const url = URL.createObjectURL(blob);
    urls.push(url);
    return h('img', { class: 'thumb-lg', src: url, alt: 'Captured photo' });
  };

  function stepper(active) {
    const steps = ['Front', 'Back', 'Review'];
    return h(
      'ol',
      { class: 'stepper' },
      steps.map((s, i) => h('li', { class: i === active ? 'on' : i < active ? 'done' : '' }, `${i + 1}. ${s}`)),
    );
  }

  function render() {
    cleanup();
    const step = !photos.front ? 0 : !photos.back ? 1 : 2;
    root.replaceChildren(h('h1', null, 'Scan new mail'), stepper(step));

    if (step < 2) {
      const side = step === 0 ? 'front' : 'back';
      root.append(
        h('h2', null, `Photograph the ${side} of the envelope`),
        step === 1 ? h('p', { class: 'hint' }, 'Flip it over: the back flap often has the return address.') : null,
      );
      widget = captureWidget({
        onPhoto: (blob) => {
          photos[side] = blob;
          render();
        },
      });
      root.append(widget.el);
      if (step === 1) {
        root.append(h('button', { class: 'btn link', type: 'button', onclick: () => ((photos.front = null), render()) }, '← Retake front'));
      }
      return;
    }

    const go = h('button', { class: 'btn primary big', type: 'button' }, 'Process & save');
    go.addEventListener('click', async () => {
      go.disabled = true;
      go.textContent = 'Processing…';
      try {
        const settings = await store.getSettings();
        const processed = await processEnvelope(photos.front, photos.back, settings);
        const mail = await store.createMail({ front: photos.front, back: photos.back, processed });
        if (processed.processing.error) toast(`Pipeline unavailable (${processed.processing.error}). Enter details manually.`, 'warn');
        location.hash = `#/mail/${mail.id}`;
      } catch (err) {
        toast(`Could not save: ${err.message}`, 'err');
        go.disabled = false;
        go.textContent = 'Process & save';
      }
    });

    root.append(
      h('h2', null, 'Check the photos'),
      h('p', { class: 'hint' }, 'Is the address readable? If not, retake before saving.'),
      h(
        'div',
        { class: 'pair' },
        h('figure', null, preview(photos.front), h('figcaption', null, 'Front'), h('button', { class: 'btn', type: 'button', onclick: () => ((photos.front = null), render()) }, 'Retake')),
        h('figure', null, preview(photos.back), h('figcaption', null, 'Back'), h('button', { class: 'btn', type: 'button', onclick: () => ((photos.back = null), render()) }, 'Retake')),
      ),
      go,
    );
  }

  render();
  return root;
}
