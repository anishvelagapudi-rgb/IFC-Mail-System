import { h, toast } from '../dom.js';
import * as auth from '../auth.js';
import * as store from '../store.js';

// Created by `python -m backend.seed`. Shown so the demo can be tried out of the box.
const DEMO_ACCOUNTS = [
  { username: 'staff', password: 'staff123', role: 'Org admin' },
  { username: 'dorothy', password: 'dorothy123', role: 'Member (Dorothy Briggs)' },
];

const field = (label, input, hint) => h('label', { class: 'field' }, h('span', null, label), input, hint ? h('small', null, hint) : null);

// mode: 'login' | 'member' (member sign-up; an admin approves it before anything else works)
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
      h('p', { class: 'hint' }, 'Staff at your organization will check your details and approve your account before you can see mail.'),
      orgs.length ? null : h('p', { class: 'hint' }, 'No organizations are set up yet.'),
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

  function demoCard() {
    return h(
      'details',
      { class: 'card demo' },
      h('summary', null, 'Try it with demo accounts'),
      h('p', { class: 'hint' }, 'Demo organization with sample data only. Never enter real member mail into a demo.'),
      h('ul', { class: 'plain-list' }, DEMO_ACCOUNTS.map((a) => h('li', null, h('strong', null, a.role), ` — ${a.username} / ${a.password}`))),
    );
  }

  async function render() {
    const tabs = [
      ['login', 'Sign in'],
      ['member', 'Create an account'],
    ];
    let form;
    try {
      form = mode === 'login' ? loginForm() : await memberForm();
    } catch (err) {
      form = h('p', { class: 'card' }, `Could not load organizations: ${err.message}`);
    }
    root.replaceChildren(
      h('h1', null, 'IFC Mail'),
      h('p', { class: 'hint' }, 'See your mail, message staff, and ask for more time, a photo, or forwarding.'),
      h('div', { class: 'tabs', role: 'tablist' }, tabs.map(([k, label]) => h('button', { class: `tab ${k === mode ? 'on' : ''}`, type: 'button', role: 'tab', 'aria-selected': k === mode, onclick: () => ((mode = k), render()) }, label))),
      form,
      demoCard(),
    );
    form.querySelector('input,select')?.focus();
  }

  render();
  return root;
}
