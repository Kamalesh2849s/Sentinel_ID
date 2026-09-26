"""
Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# ─── Auth Schemas ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str
    full_name: Optional[str]


# ─── Screening Schemas ─────────────────────────────────────────────────────────

class DocumentTypeEnum(str, Enum):
    PASSPORT = "passport"
    VISA = "visa"
    NATIONAL_ID = "national_id"
    PERMIT = "permit"
    TRAVEL_AUTH = "travel_authorization"


class ScreeningStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    FAILED = "FAILED"


class ExtractedDocumentSchema(BaseModel):
    full_name: Optional[str] = None
    document_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    nationality_code: Optional[str] = None
    issue_date: Optional[str] = None
    date_of_issue: Optional[str] = None
    date_of_issue_source: Optional[str] = "OCR/VIZ"
    expiry_date: Optional[str] = None
    sex: Optional[str] = None
    issuing_country: Optional[str] = None
    issuing_country_code: Optional[str] = None
    visa_number: Optional[str] = None
    raw_ocr_text: Optional[str] = None
    extraction_confidence: Optional[float] = None
    name_ocr: Optional[str] = None
    name_mrz: Optional[str] = None
    name_source: Optional[str] = None
    name_consistency: Optional[str] = None
    name_confidence: Optional[float] = None

    class Config:
        from_attributes = True


class CheckDigitDetailSchema(BaseModel):
    field_name: Optional[str] = None
    data: Optional[str] = None
    expected_digit: Optional[str] = None
    computed_digit: Optional[int] = None
    passed: Optional[bool] = None
    applicable: Optional[bool] = True

    class Config:
        from_attributes = True


class MRZResultSchema(BaseModel):
    mrz_detected: bool = False
    mrz_status: Optional[str] = "NOT_DETECTED"

    # Raw lines
    raw_mrz: Optional[str] = None
    raw_mrz_lines: Optional[List[str]] = []
    normalized_mrz: Optional[str] = None
    normalized_mrz_lines: Optional[List[str]] = []
    line1: Optional[str] = None
    line2: Optional[str] = None
    line3: Optional[str] = None

    # Format
    mrz_format: Optional[str] = None
    valid_structure: bool = False

    # Document fields
    document_type: Optional[str] = None
    issuing_country_code: Optional[str] = None
    nationality_code: Optional[str] = None

    # Legacy aliases
    issuing_country: Optional[str] = None
    nationality: Optional[str] = None

    document_number: Optional[str] = None
    surname: Optional[str] = None
    given_names: Optional[str] = None
    full_name: Optional[str] = None
    full_name_mrz: Optional[str] = None
    sex: Optional[str] = None
    optional_data: Optional[str] = None

    # Dates human readable
    date_of_birth: Optional[str] = None
    expiry_date: Optional[str] = None

    # Dates raw (YYMMDD)
    date_of_birth_raw: Optional[str] = None
    expiry_date_raw: Optional[str] = None

    # Date normalized objects
    date_of_birth_normalized: Optional[Dict[str, Any]] = None
    expiry_date_normalized: Optional[Dict[str, Any]] = None

    # Date of issue source tracking
    date_of_issue: Optional[str] = None
    date_of_issue_source: Optional[str] = "OCR"

    # Individual check digit results (bool)
    passport_number_check: Optional[bool] = None
    dob_check: Optional[bool] = None
    expiry_check: Optional[bool] = None
    optional_data_check: Optional[bool] = None
    composite_check: Optional[bool] = None

    # Check digit detail objects
    passport_number_check_detail: Optional[Dict[str, Any]] = None
    dob_check_detail: Optional[Dict[str, Any]] = None
    expiry_check_detail: Optional[Dict[str, Any]] = None
    optional_data_check_detail: Optional[Dict[str, Any]] = None
    composite_check_detail: Optional[Dict[str, Any]] = None

    # Structured collections
    check_digits: Optional[Dict[str, Any]] = None
    mrz_parsed_fields: Optional[Dict[str, Any]] = None
    consistency: Optional[Dict[str, Any]] = None

    # Overall
    check_digit_valid: bool = False
    all_check_digits_valid: bool = False
    field_consistency: bool = False
    failure_reasons: Optional[List[str]] = []

    class Config:
        from_attributes = True


class TamperResultSchema(BaseModel):
    tamper_detected: bool = False
    tamper_score: float = 0.0
    confidence: float = 0.0
    ela_score: float = 0.0
    consistency_score: float = 0.0
    regions: Optional[List[Dict[str, Any]]] = []
    reasons: Optional[List[str]] = []

    class Config:
        from_attributes = True


class FaceResultSchema(BaseModel):
    face_detected_document: bool = False
    face_detected_person: bool = False
    similarity: float = 0.0
    match: bool = False
    confidence: float = 0.0
    liveness_status: str = "prototype"
    failure_reason: Optional[str]

    class Config:
        from_attributes = True


class IdentityVerificationSchema(BaseModel):
    id: Optional[int] = None
    screening_id: Optional[int] = None
    document_face_detected: bool = False
    person_face_detected: bool = False
    liveness_status: str = "INCOMPLETE"
    liveness_confidence: float = 0.0
    face_similarity: float = 0.0
    face_threshold: float = 0.6
    identity_status: str = "INCOMPLETE"
    status: Optional[str] = None
    failure_reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    liveness: Optional[Dict[str, Any]] = None
    document_face: Optional[Dict[str, Any]] = None
    person_face: Optional[Dict[str, Any]] = None
    face_match: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class IdentityStartResponse(BaseModel):
    screening_id: int
    document_face_detected: bool
    document_face_quality: float = 0.0
    document_face_embedding_available: bool = False
    status: str
    message: str


class LivenessCheckResponse(BaseModel):
    screening_id: int
    liveness_status: str
    confidence: float
    frames_count: int
    details: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None


class FaceMatchResponse(BaseModel):
    screening_id: int
    person_face_detected: bool
    similarity: float
    match: bool
    threshold: float
    confidence: float = 0.0


class IdentityVerifyResponse(BaseModel):
    screening_id: int
    identity_verification: Dict[str, Any]
    screening_status: str
    risk_score: float
    message: Optional[str] = None


class ValidationResultSchema(BaseModel):
    check_name: str
    category: str
    status: str
    message: str
    severity: str

    class Config:
        from_attributes = True


class RiskReasonSchema(BaseModel):
    category: str
    severity: str
    message: str
    signal: Optional[str] = None
    result: Optional[str] = None
    impact: Optional[float] = 0.0


class RiskResultSchema(BaseModel):
    risk_score: Optional[float] = None
    risk_status: Optional[str] = "pending"
    risk_level: Optional[str] = None
    failure_reason: Optional[str] = None
    status: Optional[ScreeningStatusEnum] = None
    mrz_risk: float = 0.0
    database_risk: float = 0.0
    tamper_risk: float = 0.0
    face_risk: float = 0.0
    consistency_risk: float = 0.0
    reasons: Optional[List[Dict[str, Any]]] = []
    recommendation: Optional[str] = None
    weights_used: Optional[Dict[str, int]] = None

    class Config:
        from_attributes = True


class AuditLogSchema(BaseModel):
    action: str
    status: str
    timestamp: datetime
    action_metadata: Optional[Dict[str, Any]]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class ScreeningListItem(BaseModel):
    id: int
    document_id: str
    document_type: str
    status: str
    risk_score: Optional[float] = None
    risk: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime]
    processing_time_ms: Optional[int]
    officer_id: Optional[int]

    class Config:
        from_attributes = True


class ScreeningDetailResponse(BaseModel):
    id: int
    document_id: str
    document_type: str
    status: str
    risk_score: Optional[float] = None
    risk: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime]
    processing_time_ms: Optional[int]
    extracted_document: Optional[ExtractedDocumentSchema]
    mrz_result: Optional[MRZResultSchema]
    tamper_result: Optional[TamperResultSchema]
    face_result: Optional[FaceResultSchema]
    identity_verification: Optional[IdentityVerificationSchema] = None
    validation_results: Optional[List[ValidationResultSchema]] = []
    risk_result: Optional[RiskResultSchema]
    audit_logs: Optional[List[AuditLogSchema]] = []

    class Config:
        from_attributes = True


class ScreeningCreateResponse(BaseModel):
    screening_id: int
    document_id: str
    status: str
    message: str


class DashboardStatistics(BaseModel):
    total_screenings: int
    verified: int
    suspicious: int
    high_risk: int
    failed: int
    pending: int
    average_processing_time_ms: Optional[float]
    recent_screenings: List[ScreeningListItem]
    status_distribution: Dict[str, int]
    risk_distribution: Dict[str, int]


class ProcessingStageUpdate(BaseModel):
    stage: str
    status: str  # pending, processing, completed, failed
    message: Optional[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str]
    status_code: int
