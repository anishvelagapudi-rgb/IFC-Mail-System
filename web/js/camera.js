import { h } from './dom.js';

const MAX_EDGE = 1600;

// Downscale to a JPEG so we store/upload ~300-600 KB instead of 5+ MB phone photos.
export async function toJpeg(source, width, height) {
  const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not encode image'))), 'image/jpeg', 0.85),
  );
}

async function fileToJpeg(file) {
  const bmp = await createImageBitmap(file); // applies EXIF orientation
  try {
    return await toJpeg(bmp, bmp.width, bmp.height);
  } finally {
    bmp.close?.();
  }
}

// A capture widget: live camera preview + shutter, with a file/phone-camera fallback.
// Returns { el, stop }. Call stop() when leaving the screen to release the camera.
export function captureWidget({ onPhoto }) {
  let stream = null;
  const status = h('p', { class: 'hint' }, 'Starting camera…');
  const video = h('video', { autoplay: true, playsinline: true, muted: true });
  const shutter = h('button', { class: 'btn primary big', type: 'button', disabled: true }, 'Take photo');

  const fileInput = h('input', {
    type: 'file',
    accept: 'image/*',
    capture: 'environment',
    hidden: true,
    onchange: async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      try {
        onPhoto(await fileToJpeg(file));
      } catch {
        status.textContent = 'That file could not be read as an image.';
      }
    },
  });
  const pick = h('button', { class: 'btn', type: 'button', onclick: () => fileInput.click() }, 'Choose or take photo…');

  shutter.addEventListener('click', async () => {
    if (!video.videoWidth) return;
    shutter.disabled = true;
    try {
      onPhoto(await toJpeg(video, video.videoWidth, video.videoHeight));
    } finally {
      shutter.disabled = false;
    }
  });

  const stop = () => {
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
  };

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) {
      video.hidden = true;
      status.textContent = 'Live camera is not available here (needs https or localhost). Use “Choose or take photo”.';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      video.srcObject = stream;
      shutter.disabled = false;
      status.textContent = 'Fill the frame with the envelope, keep text sharp and glare-free.';
    } catch {
      video.hidden = true;
      status.textContent = 'Camera unavailable or permission denied. Use “Choose or take photo”.';
    }
  }
  start();

  const el = h('div', { class: 'capture' }, video, status, h('div', { class: 'row' }, shutter, pick), fileInput);
  return { el, stop };
}
