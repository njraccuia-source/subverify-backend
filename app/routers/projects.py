from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.compliance import compute_subcontractor_compliance
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Project, Subcontractor
from app.schemas import (
    ProjectCreate, ProjectOut, AssignSubcontractorRequest,
    ProjectComplianceOut, SubcontractorComplianceOut, SubcontractorOut,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_owned_project(db: Session, project_id: str, account: Account) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.account_id == account.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    project = Project(account_id=current.id, name=payload.name, address=payload.address)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    return db.query(Project).filter(Project.account_id == current.id).all()


@router.post("/{project_id}/subcontractors", response_model=ProjectOut)
def assign_subcontractor(
    project_id: str,
    payload: AssignSubcontractorRequest,
    db: Session = Depends(get_db),
    current: Account = Depends(get_current_account),
):
    project = _get_owned_project(db, project_id, current)
    sub = db.query(Subcontractor).filter(
        Subcontractor.id == payload.subcontractor_id, Subcontractor.account_id == current.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontractor not found.")

    if sub not in project.subcontractors:
        project.subcontractors.append(sub)
        db.commit()
        db.refresh(project)
    return project


@router.delete("/{project_id}/subcontractors/{subcontractor_id}", response_model=ProjectOut)
def unassign_subcontractor(
    project_id: str, subcontractor_id: str,
    db: Session = Depends(get_db), current: Account = Depends(get_current_account),
):
    project = _get_owned_project(db, project_id, current)
    sub = next((s for s in project.subcontractors if s.id == subcontractor_id), None)
    if sub:
        project.subcontractors.remove(sub)
        db.commit()
        db.refresh(project)
    return project


@router.get("/{project_id}/compliance", response_model=ProjectComplianceOut)
def project_compliance(project_id: str, db: Session = Depends(get_db), current: Account = Depends(get_current_account)):
    project = _get_owned_project(db, project_id, current)
    sub_results = []
    for sub in project.subcontractors:
        status_, approved, required = compute_subcontractor_compliance(db, sub)
        sub_results.append(SubcontractorComplianceOut(
            **SubcontractorOut.model_validate(sub).model_dump(),
            compliance_status=status_,
            documents_approved=approved,
            documents_required=required,
        ))
    return ProjectComplianceOut(project=project, subcontractors=sub_results)
