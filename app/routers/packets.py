import csv
import io
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.ai_review import review_document
from app.database import get_db
from app.dependencies import get_current_account
from app.models import (
    Account, Client, PaymentPacket, PacketDocument, PacketDocType, PacketDocStatus, PacketStatus,
)
from app.notifications import send_email
from app.schemas import (
    PublicIntakeStartRequest, PacketOut, PacketDetailOut, PacketReviewRequest, DocumentExpiryUpdateRequest,
)

router = APIRouter(tags=["payment-packets"])

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def _load_static(filename: str) -> str:
    with open(os.path.join(_STATIC_DIR, filename), encoding="utf-8") as f:
        return f.read()


JOIN_PAGE_HTML = _load_static("join_page.html")
ADMIN_PAGE_HTML = _load_static("admin.html")


def _packet_to_out(packet: PaymentPacket, request: Request | None = None) -> dict:
    data = PacketOut.model_validate(packet).model_dump()
    if request is not None:
        base = str(request.base_url).rstrip("/")
        data["upload_url"] = f"{base}/pay/{packet.public_token}"
    client = packet.client
    if client is not None:
        data["brand_name"] = client.name
        data["brand_logo_url"] = client.brand_logo_url
        data["brand_welcome_message"] = client.brand_welcome_message
    return data


def _maybe_flip_to_submitted(packet: PaymentPacket) -> None:
    if packet.status not in (PacketStatus.COLLECTING, PacketStatus.NEEDS_CHANGES):
        return
    docs_by_type = {d.doc_type: d for d in packet.documents}
    all_uploaded = all(
        docs_by_type.get(t) is not None and docs_by_type[t].status == PacketDocStatus.UPLOADED
        for t in PacketDocType.all()
    )
    if all_uploaded:
        packet.status = PacketStatus.SUBMITTED
        packet.submitted_at = datetime.utcnow()


def _owned_packet(db: Session, packet_id: str, account: Account) -> PaymentPacket:
    packet = (
        db.query(PaymentPacket)
        .join(Client)
        .filter(PaymentPacket.id == packet_id, Client.account_id == account.id)
        .first()
    )
    if not packet:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return packet


# ---------------------------------------------------------------------------
# GC-authenticated management
# ---------------------------------------------------------------------------

@router.get("/packets", response_model=list[PacketOut])
def list_packets(
    request: Request,
    client_id: str | None = None,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    q = db.query(PaymentPacket).join(Client).filter(Client.account_id == current.id)
    if client_id:
        q = q.filter(PaymentPacket.client_id == client_id)
    packets = q.order_by(PaymentPacket.created_at.desc()).all()
    return [_packet_to_out(p, request) for p in packets]


@router.get("/packets/export")
def export_packets_csv(
    client_id: str | None = None,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    q = db.query(PaymentPacket).join(Client).filter(Client.account_id == current.id)
    if client_id:
        q = q.filter(PaymentPacket.client_id == client_id)
    packets = q.order_by(PaymentPacket.created_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Client", "Subcontractor Company", "Contact Name", "Contact Email", "Job",
        "Status", "Submitted At", "Reviewed At", "Paid At", "Revision Note", "COI Expiry Date",
    ])
    for p in packets:
        coi = next((d for d in p.documents if d.doc_type == PacketDocType.INSURANCE), None)
        writer.writerow([
            p.client.name if p.client else "",
            p.subcontractor_name,
            p.contact_name,
            p.subcontractor_email,
            p.job_description or "",
            p.status.value,
            p.submitted_at.isoformat() if p.submitted_at else "",
            p.reviewed_at.isoformat() if p.reviewed_at else "",
            p.paid_at.isoformat() if p.paid_at else "",
            p.revision_note or "",
            coi.expiry_date.isoformat() if coi and coi.expiry_date else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=submissions.csv"},
    )


@router.get("/packets/{packet_id}", response_model=PacketDetailOut)
def get_packet(packet_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = _owned_packet(db, packet_id, current)
    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.patch("/packets/{packet_id}/documents/{doc_id}/expiry", response_model=PacketDetailOut)
def update_document_expiry(
    packet_id: str, doc_id: str, payload: DocumentExpiryUpdateRequest, request: Request,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    packet = _owned_packet(db, packet_id, current)
    doc = next((d for d in packet.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.expiry_date = payload.expiry_date
    db.commit()
    db.refresh(packet)
    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.delete("/packets/{packet_id}", status_code=204)
def delete_packet(packet_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = _owned_packet(db, packet_id, current)
    db.delete(packet)
    db.commit()
    return None


@router.get("/packets/{packet_id}/documents/{doc_id}/file")
def download_packet_document_file(
    packet_id: str, doc_id: str,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    packet = _owned_packet(db, packet_id, current)
    doc = next((d for d in packet.documents if d.id == doc_id), None)
    if not doc or not doc.file_data:
        raise HTTPException(status_code=404, detail="File not found.")
    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename or "document"}"'},
    )


@router.post("/packets/{packet_id}/review", response_model=PacketOut)
def review_packet(
    packet_id: str, payload: PacketReviewRequest, request: Request,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    packet = _owned_packet(db, packet_id, current)
    if packet.status != PacketStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only submissions with all three documents uploaded can be reviewed.")

    packet.reviewed_at = datetime.utcnow()
    client_name = packet.client.name

    if payload.approve:
        packet.status = PacketStatus.APPROVED
        packet.revision_note = None
        send_email(
            packet.subcontractor_email,
            f"You're all set — {client_name}",
            f"Hi {packet.contact_name},\n\nThanks — we've reviewed your submission for "
            f"\"{packet.job_description or 'your job'}\" and everything's approved. "
            f"You're cleared for payment.",
        )
    else:
        packet.status = PacketStatus.NEEDS_CHANGES
        packet.revision_note = payload.note
        base = str(request.base_url).rstrip("/")
        send_email(
            packet.subcontractor_email,
            f"A couple changes needed — {client_name}",
            f"Hi {packet.contact_name},\n\nWe reviewed your submission for "
            f"\"{packet.job_description or 'your job'}\" and need a few changes:\n\n"
            f"{payload.note}\n\nPlease update using your original link: {base}/pay/{packet.public_token}",
        )

    db.commit()
    db.refresh(packet)
    return _packet_to_out(packet, request)


@router.post("/packets/{packet_id}/mark-paid", response_model=PacketOut)
def mark_packet_paid(packet_id: str, request: Request, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    packet = _owned_packet(db, packet_id, current)
    if packet.status != PacketStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved submissions can be marked paid.")

    packet.status = PacketStatus.PAID
    packet.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(packet)
    return _packet_to_out(packet, request)


# ---------------------------------------------------------------------------
# Admin dashboard (HTML)
# ---------------------------------------------------------------------------

@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard():
    return ADMIN_PAGE_HTML


# ---------------------------------------------------------------------------
# Public, token-based routes — no login required.
# ---------------------------------------------------------------------------

@router.get("/join/{intake_token}", response_class=HTMLResponse, include_in_schema=False)
def public_join_page(intake_token: str):
    return JOIN_PAGE_HTML


@router.get("/api/public/clients/{intake_token}", tags=["public"])
def public_client_branding(intake_token: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.intake_token == intake_token).first()
    if not client:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask for a new one.")
    return {
        "brand_name": client.name,
        "brand_logo_url": client.brand_logo_url,
        "brand_welcome_message": client.brand_welcome_message,
    }


@router.post("/api/public/clients/{intake_token}/start", response_model=PacketDetailOut, tags=["public"])
def public_start_submission(
    intake_token: str, payload: PublicIntakeStartRequest, request: Request, db: Session = Depends(get_db)
):
    client = db.query(Client).filter(Client.intake_token == intake_token).first()
    if not client:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask for a new one.")

    packet = PaymentPacket(
        client_id=client.id,
        contact_name=payload.contact_name,
        subcontractor_name=payload.company_name,
        subcontractor_email=payload.contact_email,
        job_description=payload.job_description,
    )
    db.add(packet)
    db.flush()
    for doc_type in PacketDocType.all():
        db.add(PacketDocument(packet_id=packet.id, doc_type=doc_type, status=PacketDocStatus.UPLOAD_REQUIRED))
    db.commit()
    db.refresh(packet)

    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.get("/pay/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_upload_page(token: str):
    return JOIN_PAGE_HTML


@router.get("/api/public/packets/{token}", response_model=PacketDetailOut, tags=["public"])
def public_get_packet(token: str, request: Request, db: Session = Depends(get_db)):
    packet = db.query(PaymentPacket).filter(PaymentPacket.public_token == token).first()
    if not packet:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask for a new one.")
    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data


@router.post("/api/public/packets/{token}/documents", response_model=PacketDetailOut, tags=["public"])
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
    if packet.status in (PacketStatus.APPROVED, PacketStatus.PAID):
        raise HTTPException(status_code=400, detail="This submission has already been approved; uploads are locked.")

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
    doc.status = PacketDocStatus.UPLOADED
    doc.ai_verdict = review.verdict
    doc.ai_notes = review.notes
    if doc_type == PacketDocType.INVOICE:
        doc.invoice_amount_cents = invoice_amount_cents

    _maybe_flip_to_submitted(packet)
    db.commit()
    db.refresh(packet)

    data = _packet_to_out(packet, request)
    data["documents"] = packet.documents
    return data
