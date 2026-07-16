"""
AI document review.

SubVerify's real product runs each upload through an AI vision/text model that
checks the document type, legibility, and expiry before a human reviewer makes
the final call. This module is written as a pluggable interface: swap out
`_heuristic_review` for a real call to a multimodal model (e.g. the Anthropic
API with an image/PDF input) without touching any calling code.

review_document() always returns a verdict + human-readable notes; it never
blocks the upload, matching the "first-pass filter, not a hard block" behavior
described in the product.
"""
from dataclasses import dataclass
from typing import Union

from app.models import AIVerdict, DocumentType, PacketDocType

TYPE_KEYWORDS = {
    DocumentType.COI_GENERAL_LIABILITY: ["coi", "general liability", "gl", "certificate of insurance"],
    DocumentType.COI_WORKERS_COMP: ["coi", "workers comp", "wc", "certificate of insurance"],
    DocumentType.COI_AUTO: ["coi", "auto", "certificate of insurance"],
    DocumentType.CONTRACTOR_LICENSE: ["license", "contractor"],
    DocumentType.W9: ["w9", "w-9"],
    DocumentType.BUSINESS_LICENSE: ["business license", "license"],
    DocumentType.OSHA_CERTIFICATION: ["osha"],
    DocumentType.BONDING_CERTIFICATE: ["bond"],
    DocumentType.SUBCONTRACT_AGREEMENT: ["subcontract", "agreement"],
    DocumentType.ADDITIONAL_INSURED_ENDORSEMENT: ["additional insured", "endorsement"],
    # Payment-packet doc types
    "insurance": ["coi", "insurance", "certificate", "liability"],
    "w9": ["w9", "w-9"],
    "invoice": ["invoice", "quote", "estimate", "contract", "agreement"],
}


@dataclass
class ReviewResult:
    verdict: AIVerdict
    notes: str


def _heuristic_review(document_type: Union[DocumentType, PacketDocType], original_filename: str, file_size_bytes: int) -> ReviewResult:
    """A lightweight, deterministic stand-in for a real AI review call."""
    if file_size_bytes == 0:
        return ReviewResult(AIVerdict.INVALID, "Uploaded file is empty.")

    filename_lower = (original_filename or "").lower()
    keywords = TYPE_KEYWORDS.get(document_type, [])
    matched = any(kw in filename_lower for kw in keywords)

    if not filename_lower.endswith((".pdf", ".jpg", ".jpeg", ".png")):
        return ReviewResult(
            AIVerdict.FLAGGED,
            "Unrecognized file format for a compliance document. Please confirm this is the correct file.",
        )

    if matched:
        return ReviewResult(
            AIVerdict.LOOKS_VALID,
            f"Filename and document type are consistent with a {document_type.value.replace('_', ' ')} document.",
        )

    return ReviewResult(
        AIVerdict.FLAGGED,
        "Could not confirm this file matches the expected document type from its filename. Recommend manual review.",
    )


def review_document(document_type: Union[DocumentType, PacketDocType], original_filename: str, file_size_bytes: int) -> ReviewResult:
    return _heuristic_review(document_type, original_filename, file_size_bytes)
