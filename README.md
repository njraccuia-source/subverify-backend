# SubVerify-style Backend

A FastAPI backend for subcontractor compliance + a **pay-gated document link/QR**
workflow: give a subcontractor a link (or QR code), they upload their
**insurance, W-9, and invoice/quote/contract** with no login required, you
review each one, and once all three are approved the job is unlocked to pay.

It also includes the fuller compliance-tracking module (subcontractors,
projects, 10 document types, 30-day expiry alerts) if you want to grow into
that later — the two modules don't depend on each other.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # edit JWT_SECRET at minimum
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API docs (Swagger UI).

## The core flow you asked for: pay-gated document packets

1. **Sign up / log in** as a GC (`POST /auth/signup`, `POST /auth/login`) to get a bearer token.
2. **Create a packet** for a job/subcontractor:
   ```
   POST /packets
   { "subcontractor_name": "Summit Plumbing Co.", "subcontractor_email": "...", "job_description": "Bathroom rough-in" }
   ```
   Response includes `public_token` and `upload_url` (e.g. `.../pay/<token>`).
3. **Get the QR code** to text, email, or print: `GET /packets/{packet_id}/qrcode` → PNG image of the upload URL.
4. **Subcontractor opens the link** (`/pay/<token>`) on their phone — no account needed. They see three cards: Certificate of Insurance, W-9, and Invoice/Quote/Contract, each with an upload button. Uploads run through a first-pass AI review (stubbed — see `app/ai_review.py`) then wait for your review.
5. **You review each document**: `PATCH /packets/{id}/documents/{doc_id}/review` with `{"approve": true}` or `{"approve": false, "reviewer_note": "..."}`.
6. **Once all three are approved**, the packet automatically flips to `ready_to_pay`. You (or your accounting system) call `POST /packets/{id}/mark-paid` once you've actually sent payment. Until all three are approved, `mark-paid` is rejected with a 400.
7. The subcontractor's page automatically reflects status (uploaded → pending review → approved/rejected → paid), so they always know what's outstanding.

Every packet, its documents, review notes, and AI verdicts are stored — so you
have an audit trail of what was collected and approved before every payment.

## Compliance-tracking module (optional, if you grow into it)

- `POST /subcontractors` — invite a subcontractor (enforces plan limits: Starter 25 / Professional 100 / Business unlimited)
- `GET /subcontractors` — list with live compliance status (compliant / expiring_soon / non_compliant)
- `POST /subcontractors/{id}/documents` — upload one of the 10 standard document types with an expiry date
- `PATCH /documents/{id}/review` — approve/reject
- `GET /documents/expiring` — everything expiring within the alert window
- `GET /dashboard/compliance-overview` — counts for a dashboard
- A background job (`app/alerts.py`) scans daily and "sends" (logs, stubbed) 30-day expiry alerts to both GC and subcontractor.

## Project layout

```
app/
  main.py            FastAPI app, router registration, startup scheduler
  models.py           SQLAlchemy models (Account, Subcontractor, Project, Document, PaymentPacket, PacketDocument, Alert, ...)
  schemas.py           Pydantic request/response models
  security.py          Password hashing (pbkdf2_sha256) + JWT
  dependencies.py       Auth dependency (get_current_account)
  compliance.py         Compliance-status computation for subcontractors
  ai_review.py           Pluggable AI document review stub — swap in a real model call here
  alerts.py               Expiry-alert scan + APScheduler background job
  static/upload_page.html  The public, no-login upload page served at /pay/{token}
  routers/
    auth.py, subcontractors.py, projects.py, documents.py, dashboard.py, packets.py
```

## Notes on things that are stubbed for you to swap in for production

- **AI document review** (`app/ai_review.py`): currently a filename-based heuristic. Replace `_heuristic_review` with a real call — e.g. send the uploaded file to the Anthropic API for a vision/text review — the calling code doesn't need to change.
- **Email sending** (`app/alerts.py::_send_email`): currently just logs. Wire up SES/Postmark/SendGrid/etc.
- **File storage**: uploads are saved to local disk (`UPLOAD_DIR`). For production, swap in S3 or similar.
- **Payment execution**: `mark-paid` only records that payment happened — it doesn't move money. Wire it into Stripe, ACH, or however you actually pay subcontractors.
- Auth uses a simple bearer JWT per GC account. There's no subcontractor login — that's intentional, since the whole point of the packet flow is a link/QR they can use without an account.

## Tech stack

FastAPI, SQLAlchemy (SQLite by default — swap `DATABASE_URL` for Postgres in production), Pydantic v2, JWT auth (python-jose), APScheduler, `qrcode` for QR generation.
