from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance import compute_subcontractor_compliance
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Subcontractor, ComplianceStatus
from app.schemas import ComplianceOverviewOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/compliance-overview", response_model=ComplianceOverviewOut)
def compliance_overview(db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    subs = db.query(Subcontractor).filter(Subcontractor.account_id == current.id).all()

    compliant = expiring = non_compliant = 0
    for sub in subs:
        status_, _, _ = compute_subcontractor_compliance(db, sub)
        if status_ == ComplianceStatus.COMPLIANT:
            compliant += 1
        elif status_ == ComplianceStatus.EXPIRING_SOON:
            expiring += 1
        else:
            non_compliant += 1

    return ComplianceOverviewOut(
        compliant=compliant,
        expiring_soon=expiring,
        non_compliant=non_compliant,
        total_subcontractors=len(subs),
    )
