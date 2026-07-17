"""
Shared email sending. Uses Resend if RESEND_API_KEY is set; otherwise falls
back to logging only (useful for local dev without an API key).
"""
import logging

import resend

from app.config import settings

logger = logging.getLogger("subverify.notifications")

if settings.resend_api_key:
    resend.api_key = settings.resend_api_key


def send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.resend_api_key:
        logger.info("EMAIL (not sent — no RESEND_API_KEY set) -> %s | %s | %s", to_address, subject, body)
        return

    html_body = "<p>" + body.replace("\n", "<br>") + "</p>"
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": [to_address],
            "subject": subject,
            "html": html_body,
            "text": body,
        })
        logger.info("EMAIL sent -> %s | %s", to_address, subject)
    except Exception as e:
        # Never let an email failure break the request that triggered it.
        logger.error("EMAIL failed -> %s | %s | %s", to_address, subject, e)
