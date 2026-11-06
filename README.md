# IFC Mail System

A digital mail intake and notification system for people experiencing homelessness, built with input from the [Inter-Faith Council for Social Service (IFC)](https://www.ifcweb.org/) in Chapel Hill and Carrboro, NC.

> **Status:** Local demo. The staff and member web app runs on your computer with data kept in the browser. Scanned envelopes can be read by Claude through a small local server. There's no shared database, real login, or hosting yet; those are planned (Supabase + Vercel).

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
- [x] Image-processing pipeline: Claude reads envelopes, flags illegible ones instead of guessing (`server/pipeline.py`)
- [x] Eval script for the pipeline on the synthetic dataset (`server/eval_pipeline.py`)
- [ ] Benchmark results on synthetic and real (team-owned) mail photos
- [ ] Shared database and hosting (Supabase + Vercel)
- [x] Staff web UI for capturing and managing mail (prototype, browser-only storage)
- [x] Member web UI for viewing mail, messaging staff and making requests (prototype)
- [ ] Real authentication on a backend (the current login is a temporary, client-side stand-in)
- [ ] Messaging system for redirecting mail to trusted contacts
- [ ] SMS notifications and SMS-based requests
- [ ] Sender-based retention rules
- [ ] Pilot with IFC

## Repository structure

```
dataset-generator/   Synthetic envelope images + labels, and the OCR evaluator
server/              Local demo server: serves web/ and sends scanned envelopes to Claude
  app.py             run this
  pipeline.py        the Claude call (strict JSON; illegible when unsure)
  eval_pipeline.py   accuracy on the synthetic dataset
web/                 Web app: org admin side (scan mail, review, requests, messages, members, discard queue)
                     and member side (my mail, requests, messages, trusted people)
```

Planned, not yet created: shared database and hosting, `docs/` (system design and decisions).

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

### Run the demo

You need Python 3.10 or newer. No Node or build step.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
cp .env.example .env        # then paste your Claude API key into .env (optional, see below)
python server/app.py
```

Open http://localhost:8080 and click **Create demo organization and accounts**.

Demo logins: `staff` / `staff123` (org admin) and `dorothy` / `dorothy123` (member). You can also register a new organization (this creates its first admin) or a new member account under an existing organization.

- **Org admins** scan and add mail, review requests, message members, see the registration details of members who signed up with their org, manage staff logins, and run the discard queue. Each admin only sees their own organization's data.
- **Members** see photos of all their mail, message staff, and ask for more time, a photo of the contents, and/or forwarding to trusted people (names plus a forwarding address), all in one request.
- **Scanning with Claude:** when you scan an envelope, both photos go to Claude, which fills in the recipient, sender and notes. You still check and confirm every item before the member is told about it.
  - If Claude isn't confident, it flags the item **illegible** and leaves the fields blank for you instead of guessing.
  - Without an API key, scanning still works; you type the details in.

**This is a demo, not a secure system:**
- Accounts and password hashes are stored in the browser and checked in client code.
- All data lives only in this browser (IndexedDB).
- Use sample data or photos of your own mail, never real member mail.

The camera needs `localhost` or `https`. On a phone, use the "Choose or take photo" button.

### Getting a Claude API key

1. Go to https://console.anthropic.com and sign up or log in.
2. **Add credit** under **Settings → Billing**. API usage is billed separately from a Claude.ai subscription.
   - Reading one envelope with `claude-haiku-5-5` costs a small fraction of a cent, so $5 lasts a long time for a demo.
   - You can set a monthly spend limit under **Settings → Limits**.
3. **Create the key** under **Settings → API Keys → Create Key**. Name it e.g. `ifc-mail-demo` and copy it; it starts with `sk-ant-` and is shown only once.
4. **Paste it into `.env`** in the repo root, so the file reads `ANTHROPIC_API_KEY=sk-ant-...`, then restart `python server/app.py`. The startup message should say `Claude envelope reading: ON`.

**Keep the key secret.**
- `.env` is in `.gitignore`. Never commit it, paste it in chat, or put it in the web app's code.
- The key stays on the local server; the browser never sees it.
- If a key leaks, delete it in the console and create a new one.

### Tests and accuracy

```bash
python -m pytest server                    # offline, no key needed
python server/eval_pipeline.py --sample 20  # scores Claude on 20 synthetic envelopes (uses your key, about a cent)
```

The eval needs a generated dataset in `dataset-generator/dataset/` (see above).

## Privacy

This system handles mail belonging to a vulnerable population, so privacy is a core requirement, not an add-on.

- Real member mail is **never** committed to this repository or used for development or testing. Use the synthetic dataset or photos of your own mail.
- Do not commit credentials, `.env` files, or any data exported from a live deployment.
- Collect and keep only what's needed to deliver mail, and delete it when the retention period ends.
- Any use of real member data requires a consent and data-handling process agreed on with IFC.

## Team

- Anish Velagapudi
- Neil Banahatti
- Gabriel Cardenas
- Parker Kelly

## License

TBD.