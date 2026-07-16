import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.ai_review import review_document
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Subcontractor, Document, DocumentType, DocumentStatus
from app.schemas import DocumentOut, DocumentReviewRequest, ExpiringDocumentOut

router = APIRouter(tags=["documents"])


def _owned_subcontractor(db: Session, subcontractor_id: str, account: Account) -> Subcontractor:
    sub = db.query(Subcontractor).filter(
        Subcontractor.id == subcontractor_id, Subcontractor.account_id == account.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontractor not found.")
    return sub


@router.post("/subcontractors/{subcontractor_id}/documents", response_model=DocumentOut)
def upload_document(
    subcontractor_id: str,
    document_type: DocumentType = Form(...),
    expiry_date: Optional[date] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    sub = _owned_subcontractor(db, subcontractor_id, current)

    doc = db.query(Document).filter(
        Document.subcontractor_id == sub.id, Document.document_type == document_type
    ).first()
    if not doc:
        doc = Document(subcontractor_id=sub.id, document_type=document_type)
        db.add(doc)
        db.flush()

    file_bytes = file.file.read()
    review = review_document(document_type, file.filename, len(file_bytes))

    doc.file_data = file_bytes
    doc.content_type = file.content_type
    doc.original_filename = file.filename
    doc.expiry_date = expiry_date
    doc.uploaded_at = datetime.utcnow()
    doc.status = DocumentStatus.PENDING_REVIEW
    doc.ai_verdict = review.verdict
    doc.ai_notes = review.notes
    doc.reviewed_at = None
    doc.reviewer_note = None
    doc.last_alert_sent_at = None  # renewed document resets the alert clock

    db.commit()
    db.refresh(doc)
    return doc


@router.get("/subcontractors/{subcontractor_id}/documents", response_model=list[DocumentOut])
def list_subcontractor_documents(
    subcontractor_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)
):
    sub = _owned_subcontractor(db, subcontractor_id, current)
    return db.query(Document).filter(Document.subcontractor_id == sub.id).all()


@router.get("/documents/{document_id}/file")
def download_document_file(document_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    doc = (
        db.query(Document)
        .join(Subcontractor)
        .filter(Document.id == document_id, Subcontractor.account_id == current.id)
        .first()
    )
    if not doc or not doc.file_data:
        raise HTTPException(status_code=404, detail="File not found.")
    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename or "document"}"'},
    )


@router.patch("/documents/{document_id}/review", response_model=DocumentOut)
def review_document_decision(
    document_id: str,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    doc = (
        db.query(Document)
        .join(Subcontractor)
        .filter(Document.id == document_id, Subcontractor.account_id == current.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status != DocumentStatus.PENDING_REVIEW:
        raise HTTPException(status_code=400, detail="Only documents pending review can be approved or rejected.")

    doc.status = DocumentStatus.APPROVED if payload.approve else DocumentStatus.REJECTED
    doc.reviewed_at = datetime.utcnow()
    doc.reviewer_note = payload.reviewer_note

    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents/expiring", response_model=list[ExpiringDocumentOut])
def list_expiring_documents(
    db: Session = Depends(get_db), current: Account = Depends(get_current_account)
):
    today = date.today()
    docs = (
        db.query(Document)
        .join(Subcontractor)
        .filter(
            Subcontractor.account_id == current.id,
            Document.status == DocumentStatus.APPROVED,
            Document.expiry_date.isnot(None),
        )
        .all()
    )
    results = []
    for doc in docs:
        if doc.expiry_date is None:
            continue
        days_left = (doc.expiry_date - today).days
        if days_left <= settings.expiry_alert_window_days:
            results.append(ExpiringDocumentOut(
                document_id=doc.id,
                subcontractor_id=doc.subcontractor_id,
                subcontractor_name=doc.subcontractor.company_name,
                document_type=doc.document_type,
                expiry_date=doc.expiry_date,
                days_until_expiry=days_left,
            ))
    return sorted(results, key=lambda r: r.days_until_expiry)
