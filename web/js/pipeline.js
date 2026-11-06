// Image-processing adapter.
//
// If Settings -> "Pipeline URL" is set, the front/back photos are POSTed there as multipart
// form data (fields `front` and `back`, both JPEG). The endpoint should reply with JSON shaped
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
// With no URL configured (or if the call fails) the item is created empty and flagged for
// manual entry, so staff never lose a photo.

export async function processEnvelope(front, back, settings) {
  const manual = (error) => ({
    processing: { source: 'manual', ...(error ? { error } : {}) },
    legibility: null,
    sender: { name: '', organization: '', type: 'unknown' },
    recipient: { name: '' },
    notes: [],
  });

  if (!settings.pipelineUrl) return manual();

  try {
    const body = new FormData();
    body.append('front', front, 'front.jpg');
    body.append('back', back, 'back.jpg');
    const res = await fetch(settings.pipelineUrl, { method: 'POST', body });
    if (!res.ok) throw new Error(`Pipeline returned HTTP ${res.status}`);
    const j = await res.json();
    return {
      processing: { source: 'pipeline' },
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
