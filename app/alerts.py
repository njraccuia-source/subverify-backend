"""
Expiry alerts.

Scans all documents that expire within the alert window and haven't already
been alerted on today, "sends" an alert to both the GC and the subcontractor
(logged here; swap `_send_email` for a real email provider call), and records
it in the Alert table so the same expiry never double-fires same-day.
"""
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Document, DocumentStatus, Subcontractor, Account, Alert, EXPIRING_DOCUMENT_TYPES

logger = logging.getLogger("subverify.alerts")


def _send_email(to_address: str, subject: str, body: str) -> None:
    # Stub: replace with a real provider (SES, Postmark, SendGrid, etc).
    logger.info("EMAIL -> %s | %s | %s", to_address, subject, body)


def scan_and_send_expiry_alerts(db: Session) -> int:
    """Returns the number of alerts sent."""
    today = date.today()
    window_end = today + timedelta(days=settings.expiry_alert_window_days)
    sent_count = 0

    candidates = (
        db.query(Document)
        .filter(
            Document.status == DocumentStatus.APPROVED,
            Document.document_type.in_(EXPIRING_DOCUMENT_TYPES),
            Document.expiry_date.isnot(None),
            Document.expiry_date <= window_end,
        )
        .all()
    )

    for doc in candidates:
        already_alerted_today = (
            doc.last_alert_sent_at is not None
            and doc.last_alert_sent_at.date() == today
        )
        if already_alerted_today:
            continue

        subcontractor: Subcontractor = doc.subcontractor
        account: Account = subcontractor.account
        days_left = (doc.expiry_date - today).days

        _send_email(
            account.email,
            f"Compliance alert: {subcontractor.company_name} document expiring",
            f"{doc.document_type.value.replace('_', ' ').title()} for {subcontractor.company_name} "
            f"expires in {days_left} day(s) ({doc.expiry_date.isoformat()}).",
        )
        _send_email(
            subcontractor.contact_email,
            "Your compliance document is expiring soon",
            f"Your {doc.document_type.value.replace('_', ' ').title()} expires in {days_left} day(s) "
            f"({doc.expiry_date.isoformat()}). Please upload a renewed document.",
        )

        db.add(Alert(
            document_id=doc.id,
            sent_to_gc_email=account.email,
            sent_to_sub_email=subcontractor.contact_email,
            days_until_expiry=str(days_left),
        ))
        doc.last_alert_sent_at = datetime.utcnow()
        sent_count += 1

    db.commit()
    return sent_count


def _job():
    db = SessionLocal()
    try:
        count = scan_and_send_expiry_alerts(db)
        logger.info("Expiry alert scan complete: %d alert(s) sent", count)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # Runs once a day; change to a cron trigger as needed in production.
    scheduler.add_job(_job, "interval", hours=24, id="expiry_alert_scan", next_run_time=datetime.utcnow())
    scheduler.start()
    return scheduler
