from datetime import date
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Document, DocumentType, DocumentStatus, ComplianceStatus, Subcontractor, EXPIRING_DOCUMENT_TYPES
)

REQUIRED_DOCUMENT_TYPES = list(DocumentType)


def _doc_map(db: Session, subcontractor_id: str) -> Dict[DocumentType, Document]:
    docs = db.query(Document).filter(Document.subcontractor_id == subcontractor_id).all()
    # If a subcontractor somehow has duplicate rows for a type, keep the most recently uploaded.
    result: Dict[DocumentType, Document] = {}
    for d in docs:
        existing = result.get(d.document_type)
        if existing is None or (d.uploaded_at and existing.uploaded_at and d.uploaded_at > existing.uploaded_at):
            result[d.document_type] = d
    return result


def compute_subcontractor_compliance(db: Session, subcontractor: Subcontractor) -> Tuple[ComplianceStatus, int, int]:
    """
    Returns (status, approved_count, required_count).

    COMPLIANT: every required doc type is approved and not expiring within the alert window.
    EXPIRING_SOON: every required doc type is approved, but at least one expires within the window.
    NON_COMPLIANT: any required doc type is missing, rejected, pending, or already expired.
    """
    docs = _doc_map(db, subcontractor.id)
    today = date.today()
    approved_count = 0
    has_expiring = False
    fully_compliant = True

    for doc_type in REQUIRED_DOCUMENT_TYPES:
        doc = docs.get(doc_type)
        if doc is None or doc.status != DocumentStatus.APPROVED:
            fully_compliant = False
            continue

        approved_count += 1

        if doc_type in EXPIRING_DOCUMENT_TYPES and doc.expiry_date is not None:
            if doc.expiry_date < today:
                fully_compliant = False
            elif (doc.expiry_date - today).days <= settings.expiry_alert_window_days:
                has_expiring = True

    required_count = len(REQUIRED_DOCUMENT_TYPES)

    if not fully_compliant:
        return ComplianceStatus.NON_COMPLIANT, approved_count, required_count
    if has_expiring:
        return ComplianceStatus.EXPIRING_SOON, approved_count, required_count
    return ComplianceStatus.COMPLIANT, approved_count, required_count
