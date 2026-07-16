from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.compliance import compute_subcontractor_compliance
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Subcontractor, Document, DocumentType, DocumentStatus, SubcontractorStatus
from app.schemas import SubcontractorCreate, SubcontractorOut, SubcontractorComplianceOut

router = APIRouter(prefix="/subcontractors", tags=["subcontractors"])


@router.post("", response_model=SubcontractorOut, status_code=201)
def invite_subcontractor(
    payload: SubcontractorCreate,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    limit = current.subcontractor_limit()
    if limit is not None:
        existing_count = db.query(Subcontractor).filter(Subcontractor.account_id == current.id).count()
        if existing_count >= limit:
            raise HTTPException(
                status_code=402,
                detail=f"Your {current.plan.value} plan allows up to {limit} subcontractors. "
                       f"Upgrade your plan to invite more.",
            )

    sub = Subcontractor(
        account_id=current.id,
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        phone=payload.phone,
        status=SubcontractorStatus.INVITED,
    )
    db.add(sub)
    db.flush()  # get sub.id before creating child rows

    # Seed the document checklist so the sub's portal immediately shows what's required.
    for doc_type in DocumentType:
        db.add(Document(subcontractor_id=sub.id, document_type=doc_type, status=DocumentStatus.UPLOAD_REQUIRED))

    db.commit()
    db.refresh(sub)
    return sub


@router.get("", response_model=list[SubcontractorComplianceOut])
def list_subcontractors(db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    subs = db.query(Subcontractor).filter(Subcontractor.account_id == current.id).all()
    results = []
    for sub in subs:
        status_, approved, required = compute_subcontractor_compliance(db, sub)
        results.append(SubcontractorComplianceOut(
            **SubcontractorOut.model_validate(sub).model_dump(),
            compliance_status=status_,
            documents_approved=approved,
            documents_required=required,
        ))
    return results


@router.get("/{subcontractor_id}", response_model=SubcontractorComplianceOut)
def get_subcontractor(subcontractor_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    sub = db.query(Subcontractor).filter(
        Subcontractor.id == subcontractor_id, Subcontractor.account_id == current.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontractor not found.")
    status_, approved, required = compute_subcontractor_compliance(db, sub)
    return SubcontractorComplianceOut(
        **SubcontractorOut.model_validate(sub).model_dump(),
        compliance_status=status_,
        documents_approved=approved,
        documents_required=required,
    )


@router.delete("/{subcontractor_id}", status_code=204)
def remove_subcontractor(subcontractor_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    sub = db.query(Subcontractor).filter(
        Subcontractor.id == subcontractor_id, Subcontractor.account_id == current.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontractor not found.")
    db.delete(sub)
    db.commit()
    return None
