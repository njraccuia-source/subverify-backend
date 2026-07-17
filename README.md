# SubDox Backend

A backend + simple web dashboard for a **pay-gated document collection**
workflow: give a client's subcontractors one reusable link (or QR code), they
register themselves and upload **insurance, W-9, and invoice/quote/contract**,
you review all three together in a dashboard, and approve or deny with a note
— approving clears them for payment, denying emails them exactly what to fix.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env      # edit JWT_SECRET and DATABASE_URL
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/app` — that's the dashboard. No API knowledge needed from here on.

## The flow

1. **Create a client account** at `/app` — click "Create an account," one account per client (e.g. one per general contractor you work with).
2. **Log in** — you land on your dashboard, which shows:
   - Your **client link** (and QR code) — this is permanent and reusable. Give it to any subcontractor for that client.
   - **Branding** — a logo URL and welcome message shown on the subcontractor's page.
   - **Submissions** — a list that grows as subcontractors use the link.
3. **A subcontractor opens the link** (`/join/<token>`) — no login. They enter their name, company, email, and (optionally) which job it's for, then upload the three documents one at a time.
4. Once all three are in, it shows up in your dashboard as **"Needs your review."**
5. **Open it, view each file, then make one decision:**
   - **Approve** — the sub gets an email saying they're all set and cleared to pay.
   - **Deny** — you type a reason (e.g. "Need signed W-9, not blank"), the sub gets that exact note by email and can re-upload using the same link.
6. Once approved, click **Mark as paid** whenever you've actually sent payment.

Every submission — its documents, your decision, and your note — is stored, so you have a record of what was collected and approved before every payment.

**Also available per client:** search/filter submissions, export everything to CSV, delete a submission or an entire client, and set/track an expiration date on the Certificate of Insurance (shows an "Expiring soon" / "Expired" badge once you set a date).

## Where your data lives

Everything — client info, submissions, and the actual uploaded files themselves — is stored in your Postgres database (Neon). Files are saved as data inside the database, not as separate files on a server disk, so nothing is lost on redeploys or restarts. There's no separate file storage system to think about.

## Compliance-tracking module (optional, separate feature)

The backend also includes a fuller subcontractor compliance-tracking module (ongoing tracking across 10 document types, expiry alerts) if you ever want to grow into that. It's independent of the flow above and reachable via `/docs` (the API reference) rather than the dashboard.

## Project layout

```
app/
  main.py                   FastAPI app, router registration, startup scheduler
  models.py                  SQLAlchemy models (Account, PaymentPacket, PacketDocument, ...)
  schemas.py                  Pydantic request/response models
  security.py                 Password hashing (pbkdf2_sha256) + JWT
  dependencies.py              Auth dependency (get_current_account)
  ai_review.py                  Pluggable first-pass document check — swap in a real model call here
  notifications.py               Shared email-sending stub — swap in a real provider here
  alerts.py                       Expiry-alert scan for the compliance module
  static/
    join_page.html                 Subcontractor-facing: self-register + upload wizard
    admin.html                      Your dashboard: login, client link/QR, branding, review
  routers/
    auth.py, packets.py, subcontractors.py, projects.py, documents.py, dashboard.py
```

## Things stubbed for you to swap in for production

- **AI document review** (`app/ai_review.py`): currently a filename-based heuristic. Replace with a real model call if you want actual content verification.
- **Email sending** (`app/notifications.py`): sends real emails via **Resend** if `RESEND_API_KEY` is set; otherwise falls back to logging only, so local dev works without an API key.
- **Payment execution**: "Mark as paid" only records that payment happened — it doesn't move money.

## Tech stack

FastAPI, SQLAlchemy (Postgres via `DATABASE_URL`, e.g. Neon), Pydantic v2, JWT auth, `qrcode` for QR generation.

<!-- redeploy trigger -->
