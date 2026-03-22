from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constrained string types
# ---------------------------------------------------------------------------

SourceType = Literal[
    "sec_filing",
    "court_document",
    "doj_press_release",
    "fbi_press_release",
    "ftc_action",
    "fincen_action",
    "state_court",
    "newspaper_article",
    "foia_document",
    "academic_paper",
    "other",
]

CaseCategory = Literal[
    "corporate_fraud",
    "ponzi_scheme",
    "art_forgery",
    "cybercrime",
    "money_laundering",
    "embezzlement",
    "insurance_fraud",
    "identity_theft",
    "murder",
    "kidnapping",
    "organized_crime",
    "political_corruption",
    "environmental_crime",
    "trafficking",
    "other",
]

CaseStatus = Literal["researching", "ready", "assigned", "produced"]

FOIAStatus = Literal[
    "filed",
    "acknowledged",
    "processing",
    "received",
    "appealed",
    "denied",
    "partial",
]

FOIAMethod = Literal["electronic", "mail", "email"]

EntityType = Literal["person", "org", "financial", "date", "location", "legal"]

# ---------------------------------------------------------------------------
# Extracted entity (from Claude Haiku NER)
# ---------------------------------------------------------------------------


class ExtractedEntity(BaseModel):
    entity_type: EntityType
    value: str
    role: str = ""  # e.g. "defendant", "prosecutor", "victim"
    context: str = ""  # surrounding text snippet


# ---------------------------------------------------------------------------
# Per-source signal models (returned by individual search methods)
# ---------------------------------------------------------------------------


class SECFiling(BaseModel):
    accession_number: str
    company_name: str
    filing_type: str  # e.g. "10-K", "8-K", "SC 13D", "LIT-REL", "ADMIN"
    date_filed: datetime.date
    url: str
    full_text_url: str = ""
    description: str = ""


class CourtCase(BaseModel):
    case_name: str
    docket_number: str = ""
    court: str = ""
    case_type: str = ""  # "criminal", "civil", "bankruptcy"
    date_filed: datetime.date | None = None
    parties: list[str] = Field(default_factory=list)
    document_urls: list[str] = Field(default_factory=list)
    source: str = "courtlistener"  # "courtlistener", "judyrecords", state name


class PressRelease(BaseModel):
    title: str
    agency: str  # "DOJ", "FBI", "ATF", etc.
    date: datetime.date
    url: str
    summary: str = ""
    case_names: list[str] = Field(default_factory=list)
    charges: list[str] = Field(default_factory=list)


class FTCAction(BaseModel):
    case_name: str
    respondent: str = ""
    violation_type: str = ""
    settlement_amount: Decimal | None = None
    date: datetime.date | None = None
    url: str = ""


class NewsArticle(BaseModel):
    title: str
    newspaper: str = ""
    date: datetime.date | None = None
    url: str = ""
    ocr_text: str = ""
    page_info: str = ""  # e.g. "page 3, col 2"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class CaseFileCreate(BaseModel):
    case_name: str = Field(min_length=1, max_length=500)
    category: CaseCategory = "other"
    summary: str = ""


class FOIARequestInput(BaseModel):
    agency: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    case_reference: str = ""
    case_file_id: uuid.UUID | None = None
    method: FOIAMethod = "electronic"
    expected_response_date: datetime.date | None = None  # default: filed + 104 days


class FOIAUpdateInput(BaseModel):
    status: FOIAStatus | None = None
    tracking_number: str | None = None
    notes: str | None = None
    documents_received: int | None = None
    actual_response_date: datetime.date | None = None


class CollectionRequest(BaseModel):
    """Trigger automated research collection for a case or query."""

    query: str = Field(min_length=1, max_length=500)
    case_file_id: uuid.UUID | None = None
    source_types: list[SourceType] = [
        "sec_filing",
        "court_document",
        "doj_press_release",
        "ftc_action",
    ]
    filing_types: list[str] | None = None  # SEC-specific: ["10-K", "8-K", "LIT-REL"]
    date_from: datetime.date | None = None


# ---------------------------------------------------------------------------
# Response models (DB → API)
# ---------------------------------------------------------------------------


class ResearchSourceResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
                "source_type": "sec_filing",
                "title": "Wirecard AG - 6-K Filing",
                "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=wirecard",
                "source_name": "SEC EDGAR",
                "publication_date": "2020-06-18",
                "entities": [{"entity_type": "org", "value": "Wirecard AG", "role": "subject"}],
                "metadata": {"filing_type": "6-K", "accession_number": "0001193125-20-168421"},
                "relevance_score": 0.92,
                "case_file_id": "d4e5f6a7-b8c9-0123-def0-234567890123",
                "storage_path": None,
                "used_in_video_ids": [],
                "created_at": "2026-03-15T10:00:00Z",
            }
        }
    )

    id: uuid.UUID
    source_type: str
    title: str
    url: str | None
    source_name: str | None
    publication_date: datetime.date | None
    entities: list[dict[str, object]] | None = None
    metadata: dict[str, object] | None = None
    relevance_score: float | None = None
    case_file_id: uuid.UUID | None = None
    storage_path: str | None = None
    used_in_video_ids: list[uuid.UUID] | None = None
    created_at: datetime.datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ResearchSourceResponse:
        return cls.model_validate(row)


class CaseFileResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "d4e5f6a7-b8c9-0123-def0-234567890123",
                "case_name": "Wirecard AG Fraud",
                "category": "corporate_fraud",
                "summary": "Largest post-war German financial fraud — €1.9B in phantom revenue.",
                "key_entities": [
                    {"entity_type": "person", "value": "Markus Braun", "role": "defendant"},
                    {"entity_type": "org", "value": "Wirecard AG", "role": "subject"},
                ],
                "timeline": [],
                "financial_impact_usd": 2100000000,
                "source_count": 47,
                "status": "ready",
                "assigned_video_id": None,
                "assigned_topic_id": None,
                "notes": None,
                "created_at": "2026-03-10T09:00:00Z",
                "updated_at": "2026-03-15T10:00:00Z",
            }
        }
    )

    id: uuid.UUID
    case_name: str
    category: str
    summary: str | None
    key_entities: list[dict[str, object]] | None = None
    timeline: list[dict[str, object]] | None = None
    financial_impact_usd: float | None = None
    source_count: int = 0
    status: str
    assigned_video_id: uuid.UUID | None = None
    assigned_topic_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> CaseFileResponse:
        return cls.model_validate(row)


class FOIAResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "e5f6a7b8-c9d0-1234-ef01-345678901234",
                "agency": "DOJ",
                "description": "All records relating to Wirecard AG investigation 2019-2021.",
                "case_reference": "Case No. 1:20-cr-00123",
                "case_file_id": "d4e5f6a7-b8c9-0123-def0-234567890123",
                "method": "electronic",
                "tracking_number": "DOJ-2026-001234",
                "status": "processing",
                "date_filed": "2026-01-15",
                "expected_response_date": "2026-04-29",
                "actual_response_date": None,
                "documents_received": 0,
                "cost_usd": 0,
                "notes": "Initial acknowledgment received 2026-01-22.",
                "is_overdue": False,
                "created_at": "2026-01-15T10:00:00Z",
                "updated_at": "2026-01-22T14:30:00Z",
            }
        }
    )

    id: uuid.UUID
    agency: str
    description: str
    case_reference: str | None
    case_file_id: uuid.UUID | None
    method: str
    tracking_number: str | None
    status: str
    date_filed: datetime.date | None
    expected_response_date: datetime.date | None
    actual_response_date: datetime.date | None
    documents_received: int
    cost_usd: float
    notes: str | None
    is_overdue: bool = False
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> FOIAResponse:
        data = dict(row)
        exp = data.get("expected_response_date")
        status = data.get("status")
        if exp and status in ("filed", "acknowledged", "processing"):
            today = datetime.date.today()
            data["is_overdue"] = exp < today if isinstance(exp, datetime.date) else False
        return cls.model_validate(data)


class CollectionResult(BaseModel):
    sources_found: int = 0
    sources_stored: int = 0
    entities_extracted: int = 0
    source_types_searched: list[str] = Field(default_factory=list)


class ProcessedFOIAResult(BaseModel):
    foia_id: uuid.UUID
    documents_processed: int = 0
    entities_extracted: int = 0
    storage_paths: list[str] = Field(default_factory=list)
