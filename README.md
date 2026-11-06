# IFC Mail System

A digital mail intake and notification system for people experiencing homelessness, built with input from the [Inter-Faith Council for Social Service (IFC)](https://www.ifcweb.org/) in Chapel Hill and Carrboro, NC.

> **Status:** Demo-ready prototype. A Flask API on Supabase (Postgres, Auth, Storage) backs the staff and member web app, and envelopes are read with Claude vision. It runs on sample data only: it has not been piloted with IFC, and real member mail must not be used until there's a consent and data-handling process (see Privacy).

## The problem

For people without a stable address, a shelter's mail program is often the only way to receive Social Security notices, court dates, Medicaid renewals, and job offers. Mail piles up when members can't be reached or stop coming in, and time-sensitive letters can go unopened until it's too late. Staff currently have limited ways to tell members that something important has arrived or to follow up when they don't come in.

## How it works

1. **Capture.** IFC staff photograph the front and back of each incoming mail item with a phone.
2. **Extract.** The image-processing pipeline reads the sender, the intended recipient, and any extra notes (such as "Time Sensitive" or "Return Service Requested"). Items it can't read reliably are flagged as illegible for manual review instead of guessed at.
3. **Store.** The extracted data, time received, and original images are saved to a database.
4. **Notify.** The recipient is notified through their account in the web app and, where possible, by SMS.
5. **Act.** Members can:
   - request more time to pick up their mail
   - request a scanned copy
   - redirect their mail to a trusted person, such as a family member or case manager
6. **Retain.** Staff can discard mail after a retention period that depends on the sender.

## Roadmap

- [x] Synthetic envelope dataset generator with ground-truth labels and an evaluation script
- [x] Image-processing pipeline (Claude vision, strict JSON, illegible flagging instead of guessing)
- [x] Eval script that runs the pipeline on the synthetic dataset (`backend/eval_pipeline.py`)
- [ ] Benchmark results on synthetic and real (team-owned) mail photos
- [x] Database schema with org scoping and row-level security (`backend/migrations/`)
- [x] Staff web UI for capturing and managing mail
- [x] Member web UI for viewing mail, messaging staff and making requests
- [x] Real authentication (Supabase Auth), admin approval of member sign-ups
- [x] Private photo storage with short-lived signed URLs
- [x] Follow-up list for urgent unclaimed mail, with a contact log
- [ ] Real SMS (currently simulated; Twilio plugs into `backend/notifier.py`)
- [ ] SMS-based requests
- [x] Sender-based retention rules (per-org, values are placeholders to confirm with IFC)
- [ ] Pilot with IFC

## Repository structure

```
dataset-generator/      Synthetic envelope images + labels, and the OCR evaluator
backend/                Flask API (also serves web/), one deployment
  app.py                app factory, error handling, static files
  authz.py              Supabase JWT check, roles (admin / member, pending until approved)
  routes/               auth, members + approvals, mail, requests + messages, settings + follow-up
  pipeline.py           Claude vision call -> strict JSON; illegible when unsure
  matching.py           recipient name -> member
  notifier.py           SMS interface (simulated today)
  migrations/001_init.sql  tables, triggers, row-level security, storage bucket
  seed.py               demo org, logins and sample mail
  eval_pipeline.py      pipeline accuracy on the synthetic dataset
  tests/                unit tests + member-isolation test
web/                    Web app: org admin side (scan mail, review, requests, messages, members,
                        follow-up, discard queue) and member side (my mail, requests, messages, trusted people)
render.yaml             Render deployment
```

Planned, not yet created: `docs/` (system design and decisions).

*Update this section as the layout changes.*

## Getting started

Each component has its own README with setup instructions. To generate a test dataset:

```bash
cd dataset-generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup_fonts.py
python generate.py --count 5000 --seed 42 --out dataset/
```

See [`dataset-generator/README.md`](dataset-generator/README.md) for options and the evaluation script.

### Run the app locally

You need a Supabase project (free tier is fine; use a separate one for testing) and an Anthropic API key.

1. **Supabase, one-time setup** (see [Supabase setup](#supabase-setup) below).
2. **Configure:** `cp .env.example .env` and fill in the values.
3. **Install and seed:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r backend/requirements.txt
   python -m backend.seed
   ```
4. **Run:** `flask --app backend.app run --debug`, then open http://localhost:5000.

Demo logins: `staff` / `staff123` (org admin) and `dorothy` / `dorothy123` (member).

- **Org admins** scan mail (the photos are read automatically), review and confirm items, handle requests, message members, approve sign-ups, work the follow-up list, manage staff logins, and run the discard queue. They only see their own organization's data.
- **Members** sign up by choosing their organization from a list. They can't see anything until an admin approves them and links them to the right roster entry. After that they see photos of their mail, message staff, and ask for more time, a photo of the contents, and/or forwarding to trusted people.
- **Scanning:** every scanned item starts as "needs review". The member is notified only after a person confirms it. If the model is unsure, the item is flagged illegible and left unassigned instead of guessed.
- **Follow-up:** urgent mail that hasn't been picked up after N days (Settings) appears there. "Send text" is **simulated**: it writes to the follow-up log and sends nothing.

The camera needs `localhost` or `https`. On a phone, use the deployed https site or the "Choose or take photo" button.

**Tests:**

```bash
python -m pytest backend/tests                       # offline unit tests
IFC_TEST_SUPABASE=1 python -m pytest backend/tests   # also the member-isolation test (needs a TEST Supabase project)
```

The isolation test checks that a member can't read another member's mail three ways: through the API, through row-level security alone, and through the Flask checks alone. It also checks that pending sign-ups and other orgs' admins see nothing.

**Pipeline accuracy** on the synthetic dataset (this calls the API: 50 samples cost a few cents):

```bash
python -m backend.eval_pipeline --data dataset-generator/dataset --sample 50
```

### Supabase setup

1. Create a project at supabase.com.
2. **SQL editor:** paste and run `backend/migrations/001_init.sql`. It creates the tables, row-level security policies and the private `mail-images` Storage bucket.
3. **Authentication → Sign In / Providers:**
   - Keep **Email** enabled; logins are stored as `<username>@users.ifc-mail.invalid`, and no email is ever sent.
   - Turn off **Allow new users to sign up**. Accounts are created only through the API, which uses the service role.
   - Turn off **Confirm email**.
4. **Project Settings → API keys:** copy the project URL, the anon (publishable) key and the service_role (secret) key into `.env`.
   - Never put the service role key in the browser or in git.
   - If your project still uses the legacy JWT secret, also set `SUPABASE_JWT_SECRET`. Otherwise tokens are checked against the project's published signing keys.

### Deploy (Render)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo. `render.yaml` defines one web service: `gunicorn 'backend.app:create_app()'` serves both the API and the web app over HTTPS.
3. Enter the secret values when prompted: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`, and `SUPABASE_JWT_SECRET` if you need it.
4. Seed the demo data once from your machine, pointed at the production project: `python -m backend.seed`.
5. Open `https://<your-service>.onrender.com/api/health`. It should report `"ok": true` and `"pipeline": true`.

Railway works the same way: set the same variables, and use `gunicorn 'backend.app:create_app()' --bind 0.0.0.0:$PORT --timeout 120` as the start command. The free Render plan sleeps when idle, so the first request after a while takes ~30s.

## Privacy

This system handles mail belonging to a vulnerable population, so privacy is a core requirement, not an add-on.

- Real member mail is **never** committed to this repository or used for development or testing. Use the synthetic dataset or photos of your own mail.
- Do not commit credentials, `.env` files, or any data exported from a live deployment. Only `.env.example` (names, no values) is in git.
- Envelope photos live in a private Storage bucket and reach the browser only as signed links that expire after 5 minutes. Discarding an item deletes its photos.
- Each envelope is sent to the Anthropic API to be read. Check that this is covered by the data-handling agreement before using real mail.
- Collect and keep only what's needed to deliver mail, and delete it when the retention period ends.
- Any use of real member data requires a consent and data-handling process agreed on with IFC.

## Team

- Anish Velagapudi
- Neil Banahatti
- Gabriel Cardenas
- Parker Kelly

## License

TBD.