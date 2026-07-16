"""
Shared email sending. Currently a stub that logs — swap this out for a real
provider (SES, Postmark, SendGrid, etc.) in one place.
"""
import logging

logger = logging.getLogger("subverify.notifications")


def send_email(to_address: str, subject: str, body: str) -> None:
    logger.info("EMAIL -> %s | %s | %s", to_address, subject, body)
