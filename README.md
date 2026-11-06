# IFC Mail System

A digital mail intake and notification system for people experiencing homelessness, built with input from the [Inter-Faith Council for Social Service (IFC)](https://www.ifcweb.org/) in Chapel Hill and Carrboro, NC.

> **Status:** Early development. The synthetic envelope dataset generator is being built first so the image-processing pipeline can be tested before it touches real mail.

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

- [ ] Synthetic envelope dataset generator with ground-truth labels and an evaluation script
- [ ] Image-processing pipeline (text extraction plus illegible flagging)
- [ ] Benchmark the pipeline on synthetic and real (team-owned) mail photos
- [ ] Database schema for mail items, members, notifications, and requests
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
pipeline/            Image processing and text extraction (planned)
backend/             API and database (planned)
web/                 Web app: org admin side (scan mail, review, requests, messages, members, discard queue)
                     and member side (my mail, requests, messages, trusted people)
docs/                System design and decisions
```

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

To run the web app (no Node or build step needed):

```bash
python -m http.server 8080 --directory web
# open http://localhost:8080 and click "Create demo organization and accounts"
```

Demo logins: `staff` / `staff123` (org admin) and `dorothy` / `dorothy123` (member). You can also register a new organization (creates its first admin) or a new member account under an existing organization.

- **Org admins** scan and add mail, review requests, message members, see the registration details of members who signed up with their org, manage staff logins, and run the discard queue. Each admin only sees their own organization's data.
- **Members** see photos of all their mail, message staff, and ask for more time, a photo of the contents, and/or forwarding to trusted people (names plus a forwarding address), all in one request.

The login system is **temporary**: accounts and password hashes are stored in the browser and checked in client code, so it is not secure. It exists to build and test the two roles until the backend has real authentication. Data is stored only in your browser for now, so use sample data, not real member mail. The camera needs `localhost` or `https`. To test from a phone, serve over https, or use the "Choose or take photo" button.

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