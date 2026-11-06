// Image-processing adapter.
//
// Sends the front/back photos to POST /api/mail (multipart fields `front` and `back`, JPEG).
// The server stores them in private storage, runs the Claude vision pipeline
// (backend/pipeline.py), tries to match the recipient to a member, and returns the new mail
// item with status 'needs_review'. A person always confirms before the member is notified.
//
// If the pipeline is unavailable or unsure, the item still saves: it comes back with
// processing.source === 'manual' (and processing.error saying why) or legibility 'illegible',
// so staff never lose a photo and nothing is guessed.
import { createMail } from './store.js';

export async function processEnvelope(front, back) {
  return createMail({ front, back });
}
