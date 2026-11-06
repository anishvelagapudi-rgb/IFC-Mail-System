// Sample data so the UI can be tried without real mail. Images are drawn placeholders.
import * as store from './store.js';

function drawEnvelope(lines, side) {
  const c = document.createElement('canvas');
  c.width = 800;
  c.height = 560;
  const g = c.getContext('2d');
  g.fillStyle = '#6b5b4b';
  g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = '#f4efe6';
  g.fillRect(40, 40, 720, 480);
  g.strokeStyle = '#c9c0b0';
  g.strokeRect(40, 40, 720, 480);
  g.fillStyle = '#222';
  g.font = '22px monospace';
  g.fillText('SAMPLE — ' + side, 60, 75);
  g.font = '28px monospace';
  lines.forEach((l, i) => g.fillText(l, side === 'front' ? 260 : 80, (side === 'front' ? 260 : 150) + i * 40));
  return new Promise((r) => c.toBlob(r, 'image/jpeg', 0.8));
}

const DAY = 86400000;

export async function loadSampleData() {
  const dot = await store.saveMember({ name: 'Dorothy Briggs', aliases: ['Dot Briggs', 'Dorothy H Briggs'], phone: '919-555-0101', trustedContacts: [{ id: store.newId(), name: 'Marcus Lee', relationship: 'case manager', phone: '919-555-0140' }] });
  const bill = await store.saveMember({ name: 'William Ortiz', aliases: ['Bill Ortiz'], phone: '', trustedContacts: [] });
  await store.saveMember({ name: 'Renee Carter', aliases: [], phone: '919-555-0177', trustedContacts: [] });

  const items = [
    { age: 2, org: 'Department of Motor Vehicles', type: 'government', to: 'Dot Briggs', member: dot, notes: ['TIME SENSITIVE'], legib: 'clear', status: 'ready' },
    { age: 40, org: 'Summit Community Bank', type: 'bank', to: 'Bill Ortiz', member: bill, notes: ['Return Service Requested'], legib: 'degraded', status: 'ready' },
    { age: 1, org: '', type: 'unknown', to: '', member: null, notes: [], legib: 'illegible', status: 'needs_review' },
    { age: 10, org: 'Carolina Furniture Outlet', type: 'junk', to: 'Current Resident', member: null, notes: [], legib: 'clear', status: 'ready' },
    { age: 70, org: 'County Housing Authority', type: 'government', to: 'Dorothy Briggs', member: dot, notes: ['IMPORTANT INFORMATION ENCLOSED'], legib: 'clear', status: 'ready' },
  ];

  for (const it of items) {
    const label = [it.org || '(unreadable)', '', `TO: ${it.to || '???'}`, 'c/o HARBOR LIGHT', 'CHAPEL HILL, NC'];
    const front = await drawEnvelope(label, 'front');
    const back = await drawEnvelope(['(flap)'], 'back');
    const mail = await store.createMail({
      front,
      back,
      processed: {
        processing: { source: 'manual' },
        legibility: it.legib,
        sender: { name: '', organization: it.org, type: it.type },
        recipient: { name: it.to },
        notes: it.notes,
      },
    });
    mail.receivedAt = new Date(Date.now() - it.age * DAY).toISOString();
    if (it.member) mail.recipient.memberId = it.member.id;
    if (it.status === 'ready') await store.confirmMail(mail);
    else await store.saveMail(mail);
  }
}
