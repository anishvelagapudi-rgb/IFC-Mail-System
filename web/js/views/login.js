import { h, toast } from '../dom.js';
import * as auth from '../auth.js';
import * as store from '../store.js';
import * as db from '../db.js';
import { createDemoOrg, DEMO_ACCOUNTS } from '../seed.js';

const field = (label, input, hint) => h('label', { class: 'field' }, h('span', null, label), input, hint ? h('small', null, hint) : null);

// mode: 'login' | 'member' (member sign-up) | 'org' (new organization + admin)
export function loginView(mode = 'login', onDone) {
  const root = h('section', { class: 'view auth' });

  const submitting = (form, fn) => async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      await fn();
      onDone();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false;
    }
  };

  function loginForm() {
    const u = h('input', { autocomplete: 'username', required: true, autocapitalize: 'none' });
    const p = h('input', { type: 'password', autocomplete: 'current-password', required: true });
    const f = h('form', { class: 'card' }, h('h2', null, 'Sign in'), field('Username', u), field('Password', p), h('button', { class: 'btn primary', type: 'submit' }, 'Sign in'));
    f.addEventListener('submit', submitting(f, () => auth.login(u.value, p.value)));
    return f;
  }

  async function memberForm() {
    const orgs = await store.listOrgs();
    const org = h('select', { required: true }, h('option', { value: '' }, '— choose —'), orgs.map((o) => h('option', { value: o.id }, o.name)));
    const name = h('input', { required: true, autocomplete: 'name' });
    const aliases = h('input', { placeholder: 'e.g. Dot Briggs, D. H. Briggs' });
    const phone = h('input', { type: 'tel', autocomplete: 'tel' });
    const email = h('input', { type: 'email', autocomplete: 'email' });
    const u = h('input', { required: true, autocomplete: 'username', autocapitalize: 'none' });
    const p = h('input', { type: 'password', required: true, autocomplete: 'new-password' });
    const f = h(
      'form',
      { class: 'card' },
      h('h2', null, 'Create a member account'),
      orgs.length ? null : h('p', { class: 'hint' }, 'No organizations exist yet. Staff need to create one first.'),
      field('Organization that holds your mail', org),
      field('Full name', name, 'As it usually appears on your mail.'),
      field('Other names on your mail', aliases, 'Nicknames or spellings, comma-separated. Helps staff match your mail.'),
      field('Mobile phone (optional)', phone, 'For text alerts when mail arrives.'),
      field('Email (optional)', email),
      field('Username', u),
      field('Password', p, `At least ${auth.MIN_PASSWORD} characters.`),
      h('button', { class: 'btn primary', type: 'submit' }, 'Create account'),
    );
    f.addEventListener(
      'submit',
      submitting(f, () =>
        auth.registerMember({
          orgId: org.value,
          username: u.value,
          password: p.value,
          profile: { name: name.value.trim(), aliases: aliases.value.split(',').map((s) => s.trim()).filter(Boolean), phone: phone.value.trim(), email: email.value.trim(), trustedContacts: [] },
        }),
      ),
    );
    return f;
  }

  function orgForm() {
    const org = h('input', { required: true });
    const name = h('input', { required: true, autocomplete: 'name' });
    const u = h('input', { required: true, autocomplete: 'username', autocapitalize: 'none' });
    const p = h('input', { type: 'password', required: true, autocomplete: 'new-password' });
    const f = h(
      'form',
      { class: 'card' },
      h('h2', null, 'Register an organization'),
      h('p', { class: 'hint' }, 'Creates the organization and its first admin account. Admins can add more staff logins in Settings.'),
      field('Organization name', org),
      field('Your name', name),
      field('Admin username', u),
      field('Password', p, `At least ${auth.MIN_PASSWORD} characters.`),
      h('button', { class: 'btn primary', type: 'submit' }, 'Create organization'),
    );
    f.addEventListener('submit', submitting(f, () => auth.registerOrg({ orgName: org.value, name: name.value, username: u.value, password: p.value })));
    return f;
  }

  async function demoCard() {
    const users = await db.getAll('users');
    const has = users.some((u) => u.username === 'staff');
    return h(
      'details',
      { class: 'card demo', open: !users.length || has },
      h('summary', null, 'Try it with demo accounts'),
      h('p', { class: 'hint' }, 'Data is stored only in this browser. This login system is temporary and not secure, so use sample data only, never real member mail.'),
      has
        ? h('ul', { class: 'plain-list' }, DEMO_ACCOUNTS.map((a) => h('li', null, h('strong', null, a.role), ` — ${a.username} / ${a.password}`)))
        : h('button', { class: 'btn', type: 'button', onclick: async () => {
            try {
              await createDemoOrg();
              toast('Demo organization created.');
              render();
            } catch (err) {
              toast(err.message, 'err');
            }
          } }, 'Create demo organization and accounts'),
      h('button', { class: 'btn link', type: 'button', onclick: async () => {
        if (!confirm('Delete ALL organizations, accounts, mail and messages stored in this browser?')) return;
        await store.wipeEverything();
        toast('All local data deleted.');
        render();
      } }, 'Reset all local data'),
    );
  }

  async function render() {
    const tabs = [
      ['login', 'Sign in'],
      ['member', 'New member'],
      ['org', 'New organization'],
    ];
    const form = mode === 'login' ? loginForm() : mode === 'member' ? await memberForm() : orgForm();
    root.replaceChildren(
      h('h1', null, 'IFC Mail'),
      h('p', { class: 'hint' }, 'See your mail, message staff, and ask for more time, a photo, or forwarding.'),
      h('div', { class: 'tabs', role: 'tablist' }, tabs.map(([k, label]) => h('button', { class: `tab ${k === mode ? 'on' : ''}`, type: 'button', role: 'tab', 'aria-selected': k === mode, onclick: () => ((mode = k), render()) }, label))),
      form,
      await demoCard(),
    );
    form.querySelector('input,select')?.focus();
  }

  render();
  return root;
}
