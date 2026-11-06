// Shared wording for member requests (staff and member screens).
export const REQUEST_LABEL = { extra_time: 'Extra time', scan: 'Photo of contents', redirect: 'Forward to trusted person' };
export const OUTCOME_LABEL = { picked_up: 'Picked up', redirected: 'Forwarded', discarded: 'Discarded' };

export function forwardTarget(p) {
  // Older requests stored a single contactName.
  const names = p.proxyNames?.length ? p.proxyNames.join(', ') : p.contactName || 'someone';
  return `${names}${p.relationship || p.contactRelationship ? ` (${p.relationship || p.contactRelationship})` : ''}`;
}

export function describeRequest(r) {
  if (r.type === 'extra_time') return `Asked for ${r.payload.days} more day(s)`;
  if (r.type === 'scan') return 'Wants a photo of what is inside';
  const p = r.payload;
  return `Forward to ${forwardTarget(p)}${p.address ? ` at ${p.address}` : ''}${p.phone ? ` · ${p.phone}` : ''}`;
}

export const statusKind = (s) => (s === 'open' ? 'warn' : s === 'declined' ? 'muted' : 'ok');
