import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Date, Boolean, ForeignKey, Enum as SAEnum, Text, Table, LargeBinary, Integer
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Plan(str, enum.Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"


PLAN_LIMITS = {
    Plan.STARTER: {"max_subcontractors": 25, "price_cents": 7900},
    Plan.PROFESSIONAL: {"max_subcontractors": 100, "price_cents": 14900},
    Plan.BUSINESS: {"max_subcontractors": None, "price_cents": 29900},  # unlimited
}


class DocumentType(str, enum.Enum):
    COI_GENERAL_LIABILITY = "coi_general_liability"
    COI_WORKERS_COMP = "coi_workers_comp"
    COI_AUTO = "coi_auto"
    CONTRACTOR_LICENSE = "contractor_license"
    W9 = "w9"
    BUSINESS_LICENSE = "business_license"
    OSHA_CERTIFICATION = "osha_certification"
    BONDING_CERTIFICATE = "bonding_certificate"
    SUBCONTRACT_AGREEMENT = "subcontract_agreement"
    ADDITIONAL_INSURED_ENDORSEMENT = "additional_insured_endorsement"


# Document types that expire and should be tracked for expiry alerts.
# W9 and Subcontract Agreement are on-file documents without a meaningful expiry.
EXPIRING_DOCUMENT_TYPES = {
    DocumentType.COI_GENERAL_LIABILITY,
    DocumentType.COI_WORKERS_COMP,
    DocumentType.COI_AUTO,
    DocumentType.CONTRACTOR_LICENSE,
    DocumentType.BUSINESS_LICENSE,
    DocumentType.OSHA_CERTIFICATION,
    DocumentType.BONDING_CERTIFICATE,
    DocumentType.ADDITIONAL_INSURED_ENDORSEMENT,
}


class DocumentStatus(str, enum.Enum):
    UPLOAD_REQUIRED = "upload_required"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AIVerdict(str, enum.Enum):
    LOOKS_VALID = "looks_valid"
    FLAGGED = "flagged"
    INVALID = "invalid"


class ComplianceStatus(str, enum.Enum):
    COMPLIANT = "compliant"
    EXPIRING_SOON = "expiring_soon"
    NON_COMPLIANT = "non_compliant"


class SubcontractorStatus(str, enum.Enum):
    INVITED = "invited"
    ACTIVE = "active"


# ---------------------------------------------------------------------------
# Association table: subcontractors <-> projects
# ---------------------------------------------------------------------------

project_subcontractors = Table(
    "project_subcontractors",
    Base.metadata,
    Column("project_id", String, ForeignKey("projects.id"), primary_key=True),
    Column("subcontractor_id", String, ForeignKey("subcontractors.id"), primary_key=True),
    Column("assigned_at", DateTime, default=datetime.utcnow),
)


# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------

class Account(Base):
    """A general contractor's company account (the paying customer)."""
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=gen_id)
    company_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    plan = Column(SAEnum(Plan), default=Plan.STARTER, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Branding shown to subcontractors on the public upload page.
    brand_logo_url = Column(String, nullable=True)
    brand_welcome_message = Column(Text, nullable=True)

    subcontractors = relationship("Subcontractor", back_populates="account", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="account", cascade="all, delete-orphan")

    def subcontractor_limit(self):
        return PLAN_LIMITS[self.plan]["max_subcontractors"]


class Subcontractor(Base):
    __tablename__ = "subcontractors"

    id = Column(String, primary_key=True, default=gen_id)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    company_name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    status = Column(SAEnum(SubcontractorStatus), default=SubcontractorStatus.INVITED)
    invited_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="subcontractors")
    documents = relationship("Document", back_populates="subcontractor", cascade="all, delete-orphan")
    projects = relationship("Project", secondary=project_subcontractors, back_populates="subcontractors")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=gen_id)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="projects")
    subcontractors = relationship("Subcontractor", secondary=project_subcontractors, back_populates="projects")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    subcontractor_id = Column(String, ForeignKey("subcontractors.id"), nullable=False)
    document_type = Column(SAEnum(DocumentType), nullable=False)
    file_data = Column(LargeBinary, nullable=True)
    content_type = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)

    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.UPLOAD_REQUIRED)
    uploaded_at = Column(DateTime, nullable=True)
    expiry_date = Column(Date, nullable=True)

    ai_verdict = Column(SAEnum(AIVerdict), nullable=True)
    ai_notes = Column(Text, nullable=True)

    reviewed_at = Column(DateTime, nullable=True)
    reviewer_note = Column(Text, nullable=True)

    last_alert_sent_at = Column(DateTime, nullable=True)

    subcontractor = relationship("Subcontractor", back_populates="documents")


class PacketDocType(str, enum.Enum):
    INSURANCE = "insurance"          # certificate of insurance
    W9 = "w9"
    INVOICE = "invoice"              # invoice / quote / signed contract for the job

    @classmethod
    def all(cls):
        return [cls.INSURANCE, cls.W9, cls.INVOICE]


class PacketStatus(str, enum.Enum):
    COLLECTING = "collecting"        # waiting on uploads and/or review
    READY_TO_PAY = "ready_to_pay"    # all three docs approved
    PAID = "paid"


class PacketDocStatus(str, enum.Enum):
    UPLOAD_REQUIRED = "upload_required"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentPacket(Base):
    """
    A single shareable link (and QR code) for one subcontractor / one job.
    The sub uploads their COI, W-9, and invoice through the public link with
    no login required. Once a GC approves all three, the packet is cleared
    to pay.
    """
    __tablename__ = "payment_packets"

    id = Column(String, primary_key=True, default=gen_id)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    public_token = Column(String, unique=True, nullable=False, index=True, default=gen_id)

    subcontractor_name = Column(String, nullable=False)
    subcontractor_email = Column(String, nullable=True)
    job_description = Column(String, nullable=True)

    status = Column(SAEnum(PacketStatus), default=PacketStatus.COLLECTING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    account = relationship("Account")
    documents = relationship("PacketDocument", back_populates="packet", cascade="all, delete-orphan")


class PacketDocument(Base):
    __tablename__ = "packet_documents"

    id = Column(String, primary_key=True, default=gen_id)
    packet_id = Column(String, ForeignKey("payment_packets.id"), nullable=False)
    doc_type = Column(SAEnum(PacketDocType), nullable=False)

    file_data = Column(LargeBinary, nullable=True)
    content_type = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    invoice_amount_cents = Column(String, nullable=True)  # only meaningful for INVOICE type

    status = Column(SAEnum(PacketDocStatus), default=PacketDocStatus.UPLOAD_REQUIRED)
    uploaded_at = Column(DateTime, nullable=True)

    ai_verdict = Column(SAEnum(AIVerdict), nullable=True)
    ai_notes = Column(Text, nullable=True)

    reviewed_at = Column(DateTime, nullable=True)
    reviewer_note = Column(Text, nullable=True)

    packet = relationship("PaymentPacket", back_populates="documents")


class Alert(Base):
    """Log of expiry alerts sent, so we never double-send for the same document."""
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    sent_to_gc_email = Column(String, nullable=False)
    sent_to_sub_email = Column(String, nullable=False)
    days_until_expiry = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
