from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator

from app.models import Plan, DocumentType, DocumentStatus, AIVerdict, ComplianceStatus, SubcontractorStatus


# ---------------------------------------------------------------------------
# Auth / Account
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    plan: Plan = Plan.STARTER


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_name: str
    email: EmailStr
    plan: Plan
    created_at: datetime


class PlanChangeRequest(BaseModel):
    plan: Plan


# ---------------------------------------------------------------------------
# Clients (the businesses you manage — each gets its own link/branding)
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    name: str
    brand_logo_url: Optional[str] = None
    brand_welcome_message: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_welcome_message: Optional[str] = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    brand_logo_url: Optional[str] = None
    brand_welcome_message: Optional[str] = None
    intake_token: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Subcontractors
# ---------------------------------------------------------------------------

class SubcontractorCreate(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: EmailStr
    phone: Optional[str] = None


class SubcontractorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_name: str
    contact_name: Optional[str]
    contact_email: EmailStr
    phone: Optional[str]
    status: SubcontractorStatus
    invited_at: datetime


class SubcontractorComplianceOut(SubcontractorOut):
    compliance_status: ComplianceStatus
    documents_approved: int
    documents_required: int


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    address: Optional[str] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    address: Optional[str]
    is_active: bool
    created_at: datetime


class AssignSubcontractorRequest(BaseModel):
    subcontractor_id: str


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    subcontractor_id: str
    document_type: DocumentType
    original_filename: Optional[str]
    status: DocumentStatus
    uploaded_at: Optional[datetime]
    expiry_date: Optional[date]
    ai_verdict: Optional[AIVerdict]
    ai_notes: Optional[str]
    reviewed_at: Optional[datetime]
    reviewer_note: Optional[str]


class DocumentReviewRequest(BaseModel):
    approve: bool
    reviewer_note: Optional[str] = None


class ExpiringDocumentOut(BaseModel):
    document_id: str
    subcontractor_id: str
    subcontractor_name: str
    document_type: DocumentType
    expiry_date: date
    days_until_expiry: int


# ---------------------------------------------------------------------------
# Payment Packets (public link / QR upload flow)
# ---------------------------------------------------------------------------

from app.models import PacketDocType, PacketDocStatus, PacketStatus


class PublicIntakeStartRequest(BaseModel):
    """What a subcontractor fills in to identify themselves before uploading."""
    contact_name: str
    company_name: str
    contact_email: EmailStr
    job_description: Optional[str] = None


class PacketDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    doc_type: PacketDocType
    original_filename: Optional[str]
    status: PacketDocStatus
    uploaded_at: Optional[datetime]
    invoice_amount_cents: Optional[str]
    ai_verdict: Optional[AIVerdict]
    ai_notes: Optional[str]


class PacketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    client_id: str
    public_token: str
    contact_name: str
    subcontractor_name: str
    subcontractor_email: EmailStr
    job_description: Optional[str]
    status: PacketStatus
    created_at: datetime
    submitted_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    revision_note: Optional[str]
    paid_at: Optional[datetime]
    upload_url: Optional[str] = None
    brand_name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_welcome_message: Optional[str] = None


class PacketDetailOut(PacketOut):
    documents: List[PacketDocumentOut]


class PacketReviewRequest(BaseModel):
    approve: bool
    note: Optional[str] = None  # required (validated) when approve is False

    @model_validator(mode="after")
    def _require_note_on_deny(self):
        if not self.approve and not (self.note and self.note.strip()):
            raise ValueError("A note explaining what's needed is required when denying.")
        return self



class ComplianceOverviewOut(BaseModel):
    compliant: int
    expiring_soon: int
    non_compliant: int
    total_subcontractors: int


class ProjectComplianceOut(BaseModel):
    project: ProjectOut
    subcontractors: List[SubcontractorComplianceOut]
