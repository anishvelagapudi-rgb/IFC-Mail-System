// Image-processing adapter.
//
// The front/back photos are POSTed as multipart form data (fields `front` and `back`, both JPEG)
// to Settings -> "Pipeline URL", or by default to /api/extract on the local demo server
// (server/app.py), which asks Claude to read the envelope. The endpoint should reply with JSON shaped
// like the dataset-generator labels (any subset of fields):
//
//   {
//     "legibility": "clear" | "degraded" | "illegible",
//     "illegible_reason": "heavy_blur",            // optional
//     "sender":    { "name": null, "organization": "DEPARTMENT OF MOTOR VEHICLES", "sender_type": "government" },
//     "recipient": { "name": "DOT H BRIGGS" },
//     "notes": ["Return Service Requested"]
//   }
//
// If the server has no API key, Claude is unsure, or the call fails, the item is still saved
// for manual entry (or flagged illegible), so staff never lose a photo and nothing is guessed.

export async function processEnvelope(front, back, settings) {
  const manual = (error) => ({
    processing: { source: 'manual', ...(error ? { error } : {}) },
    legibility: null,
    sender: { name: '', organization: '', type: 'unknown' },
    recipient: { name: '' },
    notes: [],
  });

  const url = settings.pipelineUrl || '/api/extract';

  try {
    const body = new FormData();
    body.append('front', front, 'front.jpg');
    body.append('back', back, 'back.jpg');
    const res = await fetch(url, { method: 'POST', body });
    if (!res.ok) throw new Error(`Pipeline returned HTTP ${res.status}`);
    const j = await res.json();
    if (j.source === 'manual') return manual(j.error);
    return {
      processing: { source: j.source || 'pipeline' },
      legibility: ['clear', 'degraded', 'illegible'].includes(j.legibility) ? j.legibility : null,
      illegibleReason: j.illegible_reason || null,
      sender: {
        name: j.sender?.name || '',
        organization: j.sender?.organization || '',
        type: j.sender?.sender_type || j.sender?.type || 'unknown',
      },
      recipient: { name: j.recipient?.name || '' },
      notes: Array.isArray(j.notes) ? j.notes.map(String) : [],
    };
  } catch (err) {
    return manual(String(err.message || err));
  }
}
