// Retention rules: how long mail is held before staff may discard it, by sender type.
// The day counts below are PLACEHOLDERS - confirm real values with IFC. They are editable in Settings.

export const SENDER_TYPES = ['government', 'bank', 'healthcare', 'employer', 'personal', 'junk', 'unknown'];

export const DEFAULT_SETTINGS = {
  pipelineUrl: '',
  retentionDays: {
    government: 90,
    bank: 30,
    healthcare: 60,
    employer: 30,
    personal: 60,
    junk: 7,
    unknown: 30,
  },
};

export function baseDays(mail, settings) {
  return settings.retentionDays[mail.sender?.type || 'unknown'] ?? settings.retentionDays.unknown ?? 30;
}

// Date after which staff may discard. Approved "extra time" requests push it out.
export function discardAfter(mail, settings) {
  const days = baseDays(mail, settings) + (mail.extraDays || 0);
  return new Date(new Date(mail.receivedAt).getTime() + days * 86400000);
}

const URGENT = /time sensitive|urgent|final notice|open immediately|important|court|hearing|deadline/i;
export const isTimeSensitive = (mail) => (mail.notes || []).some((n) => URGENT.test(n));
