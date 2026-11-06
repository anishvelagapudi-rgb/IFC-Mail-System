-- IFC Mail System: initial schema.
-- Run once in the Supabase SQL editor (or `psql "$DATABASE_URL" -f backend/migrations/001_init.sql`).
--
-- Every org-owned table carries org_id, even though IFC is the only org today.
-- Access is enforced twice: in the Flask API on every endpoint, and here with row-level security.
-- Flask talks to PostgREST with the *caller's* JWT, so these policies apply to every API query.
-- Only a few admin-level actions (creating logins, Storage, seeding) use the service role.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- organizations
create table public.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  -- Per-org config. retention_days: hold period by sender type (placeholders, confirm with IFC).
  -- followup_after_days: urgent mail unclaimed this long shows on the follow-up list.
  -- min_confidence: pipeline results below this are flagged illegible for manual review.
  settings    jsonb not null default jsonb_build_object(
                'retention_days', jsonb_build_object(
                  'government', 90, 'bank', 30, 'healthcare', 60, 'employer', 30,
                  'personal', 60, 'junk', 7, 'unknown', 30),
                'followup_after_days', 3,
                'min_confidence', 0.7),
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- members (the mail roster)
-- A member is a person the org holds mail for. Staff can add one before the person has a login,
-- so envelope names can still be matched. A login is linked to a member through profiles.member_id.
create table public.members (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references public.organizations(id) on delete cascade,
  name           text not null,
  aliases        text[] not null default '{}',
  phone          text not null default '',
  email          text not null default '',
  registered_at  timestamptz,
  created_at     timestamptz not null default now()
);
create index on public.members (org_id);
-- Lets child tables use composite foreign keys that also pin org_id.
alter table public.members add constraint members_id_org_key unique (id, org_id);

-- ---------------------------------------------------------------- profiles (one per login)
create table public.profiles (
  user_id       uuid primary key references auth.users(id) on delete cascade,
  org_id        uuid not null references public.organizations(id) on delete cascade,
  role          text not null check (role in ('admin', 'member')),
  -- New member sign-ups start 'pending' and can do nothing until an admin approves them.
  status        text not null default 'pending' check (status in ('pending', 'active', 'rejected')),
  username      text not null unique check (username ~ '^[a-z0-9._-]{3,32}$'),
  display_name  text not null default '',
  member_id     uuid unique references public.members(id) on delete set null,
  -- What the person typed at sign-up (name, aliases, phone, email), shown to the approving admin.
  registration  jsonb not null default '{}'::jsonb,
  approved_by   uuid references auth.users(id) on delete set null,
  approved_at   timestamptz,
  created_at    timestamptz not null default now(),
  check (role = 'admin' or status <> 'active' or member_id is not null)
);
create index on public.profiles (org_id);

-- ---------------------------------------------------------------- trusted contacts
create table public.trusted_contacts (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null,
  member_id     uuid not null,
  name          text not null,
  relationship  text not null default '',
  phone         text not null default '',
  address       text not null default '',
  created_at    timestamptz not null default now(),
  foreign key (member_id, org_id) references public.members(id, org_id) on delete cascade
);
create index on public.trusted_contacts (member_id);

-- ---------------------------------------------------------------- mail items
create table public.mail_items (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references public.organizations(id) on delete cascade,
  member_id          uuid,
  recipient_raw      text not null default '',
  sender_name        text not null default '',
  sender_org         text not null default '',
  sender_type        text not null default 'unknown'
                     check (sender_type in ('government','bank','healthcare','employer','personal','junk','unknown')),
  notes              text[] not null default '{}',
  urgent             boolean not null default false,          -- set by trigger (model flag or note keywords)
  legibility         text check (legibility in ('clear','degraded','illegible')),
  illegible          boolean generated always as (coalesce(legibility = 'illegible', false)) stored,
  illegible_reason   text,
  confidence         real,
  status             text not null default 'needs_review' check (status in ('needs_review','ready','closed')),
  outcome            text check (outcome in ('picked_up','redirected','discarded')),
  received_at        timestamptz not null default now(),
  extra_days         integer not null default 0 check (extra_days >= 0),
  hold_until         timestamptz,                              -- set by trigger from org retention settings
  front_image_path   text,
  back_image_path    text,
  scan_image_paths   text[] not null default '{}',
  extraction         jsonb,                                    -- raw model response + processing metadata
  redirected_to      text,
  notified_at        timestamptz,
  closed_at          timestamptz,
  created_at         timestamptz not null default now(),
  foreign key (member_id, org_id) references public.members(id, org_id) on delete set null (member_id),
  unique (id, org_id)
);
create index on public.mail_items (org_id, status);
create index on public.mail_items (member_id);

-- ---------------------------------------------------------------- requests
create table public.requests (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null,
  mail_id      uuid not null,
  member_id    uuid not null,
  type         text not null check (type in ('extra_time','scan','redirect')),
  status       text not null default 'open' check (status in ('open','approved','declined','fulfilled')),
  payload      jsonb not null default '{}'::jsonb,
  resolved_at  timestamptz,
  created_at   timestamptz not null default now(),
  foreign key (mail_id, org_id) references public.mail_items(id, org_id) on delete cascade,
  foreign key (member_id, org_id) references public.members(id, org_id) on delete cascade
);
create index on public.requests (org_id, status);
create index on public.requests (mail_id);

-- ---------------------------------------------------------------- messages
-- mail_id null = a general conversation between the member and staff.
create table public.messages (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null,
  member_id       uuid not null,
  mail_id         uuid,
  request_id      uuid references public.requests(id) on delete set null,
  sender          text not null check (sender in ('staff','member','system')),
  author_id       uuid references auth.users(id) on delete set null,
  body            text not null check (length(body) between 1 and 4000),
  seen_by_staff   boolean not null default false,
  seen_by_member  boolean not null default false,
  created_at      timestamptz not null default now(),
  foreign key (member_id, org_id) references public.members(id, org_id) on delete cascade,
  foreign key (mail_id, org_id) references public.mail_items(id, org_id) on delete cascade
);
create index on public.messages (org_id, member_id);

-- ---------------------------------------------------------------- notifications
-- Queued member notifications (in-app now; SMS delivery plugs in via backend/notifier.py).
create table public.notifications (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null,
  mail_id     uuid not null,
  member_id   uuid not null,
  channels    text[] not null default '{app}',
  body        text not null,
  status      text not null default 'queued' check (status in ('queued','sent','failed','simulated')),
  created_at  timestamptz not null default now(),
  foreign key (mail_id, org_id) references public.mail_items(id, org_id) on delete cascade,
  foreign key (member_id, org_id) references public.members(id, org_id) on delete cascade
);
create index on public.notifications (mail_id);

-- ---------------------------------------------------------------- follow-up log
-- Every attempt to reach a member about urgent, unclaimed mail. No real SMS yet: texts are
-- written here with simulated = true.
create table public.followup_log (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null,
  mail_id     uuid not null,
  member_id   uuid,
  admin_id    uuid references auth.users(id) on delete set null,
  channel     text not null check (channel in ('sms','phone','in_person','other')),
  simulated   boolean not null default false,
  outcome     text not null default '',
  note        text not null default '',
  created_at  timestamptz not null default now(),
  foreign key (mail_id, org_id) references public.mail_items(id, org_id) on delete cascade,
  foreign key (member_id, org_id) references public.members(id, org_id) on delete set null (member_id)
);
create index on public.followup_log (mail_id);

-- ================================================================ derived fields
-- urgent: the model's flag OR a time-sensitive endorsement in the notes.
-- hold_until: received_at + the org's retention days for this sender type + granted extra days.
create or replace function public.mail_items_derive() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  days integer;
begin
  select coalesce((o.settings -> 'retention_days' ->> new.sender_type)::int,
                  (o.settings -> 'retention_days' ->> 'unknown')::int, 30)
    into days from public.organizations o where o.id = new.org_id;
  new.hold_until := new.received_at + make_interval(days => days + new.extra_days);
  new.urgent := coalesce((new.extraction -> 'model' ->> 'urgent')::boolean, false)
             or array_to_string(new.notes, ' ') ~* '(time sensitive|urgent|final notice|open immediately|important|court|hearing|deadline)';
  return new;
end $$;

create trigger mail_items_derive before insert or update on public.mail_items
  for each row execute function public.mail_items_derive();

-- When an org changes its retention settings, recompute hold_until for its mail.
create or replace function public.organizations_settings_changed() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.settings is distinct from old.settings then
    update public.mail_items set received_at = received_at where org_id = new.id;
  end if;
  return new;
end $$;

create trigger organizations_settings_changed after update on public.organizations
  for each row execute function public.organizations_settings_changed();

-- ================================================================ row-level security
-- Helpers read the caller's *active* profile. A pending or rejected login gets nulls, so every
-- policy below denies it.
create or replace function public.auth_org_id() returns uuid
language sql stable security definer set search_path = public as $$
  select org_id from public.profiles where user_id = auth.uid() and status = 'active'
$$;
create or replace function public.auth_is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select role = 'admin' from public.profiles where user_id = auth.uid() and status = 'active'), false)
$$;
create or replace function public.auth_member_id() returns uuid
language sql stable security definer set search_path = public as $$
  select member_id from public.profiles where user_id = auth.uid() and status = 'active' and role = 'member'
$$;

alter table public.organizations    enable row level security;
alter table public.profiles         enable row level security;
alter table public.members          enable row level security;
alter table public.trusted_contacts enable row level security;
alter table public.mail_items       enable row level security;
alter table public.requests         enable row level security;
alter table public.messages         enable row level security;
alter table public.notifications    enable row level security;
alter table public.followup_log     enable row level security;

-- organizations: anyone with a profile in the org (even pending) can read its name/settings;
-- admins can update settings. The public sign-up dropdown is served by the API with the service role.
create policy org_read on public.organizations for select to authenticated
  using (exists (select 1 from public.profiles p where p.user_id = auth.uid() and p.org_id = organizations.id));
create policy org_admin_update on public.organizations for update to authenticated
  using (public.auth_is_admin() and id = public.auth_org_id())
  with check (public.auth_is_admin() and id = public.auth_org_id());

-- profiles: you can read your own row; admins read and update (approve/reject) their org's rows.
-- Inserts happen only through the API with the service role.
create policy profile_self_read on public.profiles for select to authenticated
  using (user_id = auth.uid());
create policy profile_admin_read on public.profiles for select to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id());
create policy profile_admin_update on public.profiles for update to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());

-- members
create policy members_admin_all on public.members for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy members_self_read on public.members for select to authenticated
  using (id = public.auth_member_id());
create policy members_self_update on public.members for update to authenticated
  using (id = public.auth_member_id())
  with check (id = public.auth_member_id() and org_id = public.auth_org_id());

-- trusted contacts
create policy tc_admin_all on public.trusted_contacts for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy tc_self_all on public.trusted_contacts for all to authenticated
  using (member_id = public.auth_member_id())
  with check (member_id = public.auth_member_id() and org_id = public.auth_org_id());

-- mail: members only see confirmed mail addressed to them (unconfirmed items may be mis-matched).
create policy mail_admin_all on public.mail_items for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy mail_member_read on public.mail_items for select to authenticated
  using (member_id = public.auth_member_id() and status <> 'needs_review');

-- requests: members read theirs and open new ones on their own visible mail.
create policy req_admin_all on public.requests for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy req_member_read on public.requests for select to authenticated
  using (member_id = public.auth_member_id());
create policy req_member_insert on public.requests for insert to authenticated
  with check (
    member_id = public.auth_member_id() and status = 'open'
    and exists (select 1 from public.mail_items m where m.id = mail_id and m.org_id = requests.org_id
                and m.member_id = public.auth_member_id() and m.status = 'ready'));

-- messages
create policy msg_admin_all on public.messages for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy msg_member_read on public.messages for select to authenticated
  using (member_id = public.auth_member_id());
create policy msg_member_insert on public.messages for insert to authenticated
  with check (
    member_id = public.auth_member_id() and sender = 'member' and org_id = public.auth_org_id()
    and (mail_id is null or exists (select 1 from public.mail_items m where m.id = mail_id
         and m.member_id = public.auth_member_id() and m.status <> 'needs_review')));
create policy msg_member_update on public.messages for update to authenticated
  using (member_id = public.auth_member_id())
  with check (member_id = public.auth_member_id());

-- notifications: written by admins (when mail is confirmed), readable by the recipient.
create policy notif_admin_all on public.notifications for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());
create policy notif_member_read on public.notifications for select to authenticated
  using (member_id = public.auth_member_id());

-- follow-up log: admins only.
create policy fu_admin_all on public.followup_log for all to authenticated
  using (public.auth_is_admin() and org_id = public.auth_org_id())
  with check (public.auth_is_admin() and org_id = public.auth_org_id());

-- Members may update only their own contact details and the "seen" flag; the API whitelists
-- fields too, but column privileges make it a hard rule for any member-role write.
revoke update on public.messages from authenticated;
grant update (seen_by_staff, seen_by_member) on public.messages to authenticated;

-- Nothing is readable without logging in.
revoke all on all tables in schema public from anon;

-- ================================================================ storage
-- Private bucket for envelope photos and content scans. No storage policies are granted to
-- end users: the API uploads and signs short-lived URLs with the service role after its own
-- access check. Paths: {org_id}/{mail_id}/{front|back|scan-<n>}.jpg
insert into storage.buckets (id, name, public)
values ('mail-images', 'mail-images', false)
on conflict (id) do nothing;
