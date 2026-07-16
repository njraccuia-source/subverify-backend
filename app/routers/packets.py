import io
import os
from datetime import datetime

import qrcode
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.ai_review import review_document
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_account
from app.models import (
    Account, PaymentPacket, PacketDocument, PacketDocType, PacketDocStatus, PacketStatus,
)
from app.schemas import PacketCreate, PacketOut, PacketDetailOut, PacketDocReviewRequest

router = APIRouter(tags=["payment-packets"])

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
with open(os.path.join(_STATIC_DIR, "upload_page.html"), encoding="utf-8") as _f:
    UPLOAD_PAGE_HTML = _f.read()


def _packet_to_out(packet: PaymentPacket, request: Request | None = None) -> dict:
    data = PacketOut.model_validate(packet).model_dump()
    if request is not None:
        base = str(request.base_url).rstrip("/")
        data["upload_url"] = f"{base}/pay/{packet.public_token}"
    account = packet.account
    if account is not None:
        data["brand_name"] = account.company_name
        data["brand_logo_url"] = account.brand_logo_url
        data["brand_welcome_message"] = account.brand_welcome_message
    return data


def _refresh_packet_status(db: Session, packet: PaymentPacket) -> None:
    """Ready to pay once all three doc types are uploaded AND approved."""
    docs_by_type = {d.doc_type: d for d in packet.documents}
    all_approved = all(
        docs_by_type.get(t) is not None and docs_by_type[t].status == PacketDocStatus.APPROVED
        for t in PacketDocType.all()
    )
    if packet.status == PacketStatus.PAID:
        return  # never move a paid packet backwards
    packet.status = PacketStatus.READY_TO_PAY if all_approved else PacketStatus.COLLECTING


# ---------------------------------------------------------------------------
# GC-authenticated management
# ---------------------------------------------------------------------------

@router.post("/packets", response_model=PacketOut, status_code=201)
def create_packet(
    payload: PacketCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    packet = PaymentPacket(
        account_id=current.id,
        subcontractor_name=payload.subcontractor_name,
        subcontractor_email=payload.subcontractor_email,
        job_description=payload.job_description,
    )
    db.add(packet)
    db.flush()

    for doc_type in PacketDocType.all():
        db.add(PacketDocument(packet_id=packet.id, doc_type=doc_type, status=PacketDocStatus.UPLOAD_REQUIRED))

    db.commit()
    db.refresh(packet)
    return _packet_to_out(packet, request)


@router.get("/packets", response_model=list[PacketOut])
def list_packets(request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packets = db.query(PaymentPacket).filter(PaymentPacket.account_id == current.id).all()
    return [_packet_to_out(p, request) for p in packets]


@router.get("/packets/{packet_id}", response_model=PacketDetailOut)
def get_packet(packet_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = db.query(PaymentPacket).filter(
        PaymentPacket.id == packet_id, PaymentPacket.account_id == current.id
    ).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found.")
    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.get("/packets/{packet_id}/qrcode")
def packet_qrcode(packet_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = db.query(PaymentPacket).filter(
        PaymentPacket.id == packet_id, PaymentPacket.account_id == current.id
    ).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found.")

    base = str(request.base_url).rstrip("/")
    upload_url = f"{base}/pay/{packet.public_token}"

    img = qrcode.make(upload_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.patch("/packets/{packet_id}/documents/{doc_id}/review", response_model=PacketDetailOut)
def review_packet_document(
    packet_id: str, doc_id: str, payload: PacketDocReviewRequest, request: Request,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    packet = db.query(PaymentPacket).filter(
        PaymentPacket.id == packet_id, PaymentPacket.account_id == current.id
    ).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found.")

    doc = next((d for d in packet.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status != PacketDocStatus.PENDING_REVIEW:
        raise HTTPException(status_code=400, detail="Only documents pending review can be approved or rejected.")

    doc.status = PacketDocStatus.APPROVED if payload.approve else PacketDocStatus.REJECTED
    doc.reviewed_at = datetime.utcnow()
    doc.reviewer_note = payload.reviewer_note

    _refresh_packet_status(db, packet)
    db.commit()
    db.refresh(packet)

    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.post("/packets/{packet_id}/mark-paid", response_model=PacketOut)
def mark_packet_paid(packet_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = db.query(PaymentPacket).filter(
        PaymentPacket.id == packet_id, PaymentPacket.account_id == current.id
    ).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found.")
    if packet.status != PacketStatus.READY_TO_PAY:
        raise HTTPException(status_code=400, detail="Packet is not cleared to pay yet — all three documents must be approved first.")

    packet.status = PacketStatus.PAID
    packet.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(packet)
    return _packet_to_out(packet, request)


# ---------------------------------------------------------------------------
# Public, token-based routes — no login required. This is what the
# subcontractor sees when they scan the QR code or open the link.
# ---------------------------------------------------------------------------

@router.get("/pay/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_upload_page(token: str):
    """Serves the mobile-friendly upload page the subcontractor sees when they
    scan the QR code or open the link. The page itself talks to the JSON API
    below (/api/public/packets/{token})."""
    return UPLOAD_PAGE_HTML


@router.get("/api/public/packets/{token}", response_model=PacketDetailOut)
def public_get_packet(token: str, request: Request, db: Session = Depends(get_db)):
    packet = db.query(PaymentPacket).filter(PaymentPacket.public_token == token).first()
    if not packet:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask for a new one.")
    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.post("/api/public/packets/{token}/documents", response_model=PacketDetailOut)
def public_upload_document(
    token: str,
    doc_type: PacketDocType = Form(...),
    invoice_amount_cents: str | None = Form(None),
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    packet = db.query(PaymentPacket).filter(PaymentPacket.public_token == token).first()
    if not packet:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask for a new one.")
    if packet.status == PacketStatus.PAID:
        raise HTTPException(status_code=400, detail="This job has already been paid; documents are locked.")

    doc = next((d for d in packet.documents if d.doc_type == doc_type), None)
    if not doc:
        doc = PacketDocument(packet_id=packet.id, doc_type=doc_type)
        db.add(doc)
        db.flush()

    file_bytes = file.file.read()
    review = review_document(doc_type, file.filename, len(file_bytes))

    doc.file_data = file_bytes
    doc.content_type = file.content_type
    doc.original_filename = file.filename
    doc.uploaded_at = datetime.utcnow()
    doc.status = PacketDocStatus.PENDING_REVIEW
    doc.ai_verdict = review.verdict
    doc.ai_notes = review.notes
    doc.reviewed_at = None
    doc.reviewer_note = None
    if doc_type == PacketDocType.INVOICE:
        doc.invoice_amount_cents = invoice_amount_cents

    _refresh_packet_status(db, packet)
    db.commit()
    db.refresh(packet)

    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.get("/packets/{packet_id}/documents/{doc_id}/file")
def download_packet_document_file(
    packet_id: str, doc_id: str,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    packet = db.query(PaymentPacket).filter(
        PaymentPacket.id == packet_id, PaymentPacket.account_id == current.id
    ).first()
    if not packet:
        raise HTTPException(status_code=404, detail="Packet not found.")
    doc = next((d for d in packet.documents if d.id == doc_id), None)
    if not doc or not doc.file_data:
        raise HTTPException(status_code=404, detail="File not found.")
    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename or "document"}"'},
    )
