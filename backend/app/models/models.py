"""
SQLAlchemy ORM models for SentinelID.
All models are defined here and imported by the database init.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class UserRole(str, enum.Enum):
    OFFICER = "officer"
    ADMIN = "admin"
    SUPERVISOR = "supervisor"


class ScreeningStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    FAILED = "FAILED"


class DocumentType(str, enum.Enum):
    PASSPORT = "passport"
    VISA = "visa"
    NATIONAL_ID = "national_id"
    PERMIT = "permit"
    TRAVEL_AUTH = "travel_authorization"


class User(Base):
    """Officer/admin user accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(SAEnum(UserRole), default=UserRole.OFFICER)
    badge_number = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)

    screenings = relationship("Screening", back_populates="officer")


class Screening(Base):
    """Master screening record."""
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    document_type = Column(SAEnum(DocumentType), default=DocumentType.PASSPORT)
    status = Column(SAEnum(ScreeningStatus), default=ScreeningStatus.PENDING)
    risk_score = Column(Float, nullable=True, default=None)
    image_path = Column(String(500))
    person_image_path = Column(String(500))
    officer_id = Column(Integer, ForeignKey("users.id"))
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    officer = relationship("User", back_populates="screenings")
    extracted_document = relationship("ExtractedDocument", back_populates="screening", uselist=False)
    mrz_result = relationship("MRZResult", back_populates="screening", uselist=False)
    tamper_result = relationship("TamperResult", back_populates="screening", uselist=False)
    face_result = relationship("FaceResult", back_populates="screening", uselist=False)
    validation_results = relationship("ValidationResult", back_populates="screening")
    audit_logs = relationship("AuditLog", back_populates="screening")
    risk_result = relationship("RiskResult", back_populates="screening", uselist=False)
    identity_verification = relationship("IdentityVerification", back_populates="screening", uselist=False)


class ExtractedDocument(Base):
    """OCR-extracted document fields."""
    __tablename__ = "extracted_documents"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    full_name = Column(String(200))
    document_number = Column(String(50), index=True)
    date_of_birth = Column(String(20))
    nationality = Column(String(100))
    issue_date = Column(String(20))
    expiry_date = Column(String(20))
    sex = Column(String(10))
    issuing_country = Column(String(100))
    visa_number = Column(String(50))
    raw_ocr_text = Column(Text)
    extraction_confidence = Column(Float, default=0.0)
    nationality_code = Column(String(10), nullable=True)
    issuing_country_code = Column(String(10), nullable=True)
    date_of_issue = Column(String(20), nullable=True)
    date_of_issue_source = Column(String(50), nullable=True, default="OCR/VIZ")
    name_ocr = Column(String(200), nullable=True)
    name_mrz = Column(String(200), nullable=True)
    name_source = Column(String(50), nullable=True)
    name_consistency = Column(String(50), nullable=True)
    name_confidence = Column(Float, nullable=True)

    screening = relationship("Screening", back_populates="extracted_document")


class MRZResult(Base):
    """MRZ extraction and validation results."""
    __tablename__ = "mrz_results"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    mrz_detected = Column(Boolean, default=False)
    mrz_status = Column(String(50), default="NOT_DETECTED")
    raw_mrz = Column(Text)
    raw_mrz_lines = Column(JSON, nullable=True)
    normalized_mrz = Column(Text, nullable=True)
    normalized_mrz_lines = Column(JSON, nullable=True)
    mrz_format = Column(String(10))  # TD1, TD2, TD3
    valid_structure = Column(Boolean, default=False)
    check_digit_valid = Column(Boolean, default=False)
    document_number = Column(String(50))
    date_of_birth = Column(String(20))
    expiry_date = Column(String(20))
    nationality = Column(String(10))
    nationality_code = Column(String(10), nullable=True)
    issuing_country = Column(String(10))
    issuing_country_code = Column(String(10), nullable=True)
    surname = Column(String(100))
    given_names = Column(String(100))
    sex = Column(String(5))
    field_consistency = Column(Boolean, default=False)
    failure_reasons = Column(JSON)
    check_digits = Column(JSON, nullable=True)
    mrz_parsed_fields = Column(JSON, nullable=True)

    screening = relationship("Screening", back_populates="mrz_result")


class TamperResult(Base):
    """Document tamper detection results."""
    __tablename__ = "tamper_results"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    tamper_detected = Column(Boolean, default=False)
    tamper_score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    ela_score = Column(Float, default=0.0)
    consistency_score = Column(Float, default=0.0)
    regions = Column(JSON)
    reasons = Column(JSON)

    screening = relationship("Screening", back_populates="tamper_result")


class FaceResult(Base):
    """Face verification results."""
    __tablename__ = "face_results"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    face_detected_document = Column(Boolean, default=False)
    face_detected_person = Column(Boolean, default=False)
    similarity = Column(Float, default=0.0)
    match = Column(Boolean, default=False)
    confidence = Column(Float, default=0.0)
    liveness_status = Column(String(50), default="prototype")
    failure_reason = Column(String(500))

    screening = relationship("Screening", back_populates="face_result")


class IdentityVerification(Base):
    """
    Mandatory identity verification record storing liveness and face match decision.
    Combines document face, person face, temporal liveness, and face similarity.
    """
    __tablename__ = "identity_verifications"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    document_face_detected = Column(Boolean, default=False)
    person_face_detected = Column(Boolean, default=False)
    liveness_status = Column(String(50), default="INCOMPLETE")  # PASS, FAIL, INCONCLUSIVE, INCOMPLETE
    liveness_confidence = Column(Float, default=0.0)
    face_similarity = Column(Float, default=0.0)
    face_threshold = Column(Float, default=0.6)
    identity_status = Column(String(50), default="INCOMPLETE")  # PASS, FAIL, INCOMPLETE
    failure_reason = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    screening = relationship("Screening", back_populates="identity_verification")

    @property
    def status(self) -> str:
        return self.identity_status

    @property
    def liveness(self) -> Dict[str, Any]:
        if self.details and "liveness" in self.details:
            return self.details["liveness"]
        return {"status": self.liveness_status, "confidence": self.liveness_confidence}

    @property
    def document_face(self) -> Dict[str, Any]:
        if self.details and "document_face" in self.details:
            return self.details["document_face"]
        return {"detected": self.document_face_detected}

    @property
    def person_face(self) -> Dict[str, Any]:
        if self.details and "person_face" in self.details:
            return self.details["person_face"]
        return {"detected": self.person_face_detected}

    @property
    def face_match(self) -> Dict[str, Any]:
        if self.details and "face_match" in self.details:
            return self.details["face_match"]
        return {
            "similarity": self.face_similarity,
            "threshold": self.face_threshold,
            "status": "PASS" if self.face_similarity >= self.face_threshold else "FAIL",
        }


class ValidationResult(Base):
    """Individual validation check results."""
    __tablename__ = "validation_results"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"))
    check_name = Column(String(100))
    category = Column(String(50))  # document, mrz, identity, database
    status = Column(String(20))    # PASS, FAIL, WARNING, SKIPPED
    message = Column(Text)
    severity = Column(String(20))  # LOW, MEDIUM, HIGH

    screening = relationship("Screening", back_populates="validation_results")


class RiskResult(Base):
    """Final risk scoring and explanation."""
    __tablename__ = "risk_results"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), unique=True)
    risk_score = Column(Float, nullable=True, default=None)
    risk_status = Column(String(50), default="pending")  # pending, calculating, completed, unavailable, failed
    risk_level = Column(String(50), nullable=True)  # low, medium, high
    failure_reason = Column(String(500), nullable=True)
    status = Column(SAEnum(ScreeningStatus), nullable=True)
    mrz_risk = Column(Float, default=0.0)
    database_risk = Column(Float, default=0.0)
    tamper_risk = Column(Float, default=0.0)
    face_risk = Column(Float, default=0.0)
    consistency_risk = Column(Float, default=0.0)
    reasons = Column(JSON)
    recommendation = Column(Text)
    weights_used = Column(JSON)
    calculated_at = Column(DateTime, nullable=True)

    screening = relationship("Screening", back_populates="risk_result")


class AuditLog(Base):
    """Audit trail for every screening action."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"))
    action = Column(String(100), nullable=False)
    status = Column(String(20))  # SUCCESS, FAILED
    timestamp = Column(DateTime, default=datetime.utcnow)
    action_metadata = Column(JSON)
    error_message = Column(Text)

    screening = relationship("Screening", back_populates="audit_logs")


# ─── Mock / Prototype Reference Databases ─────────────────────────────────────

class ValidDocument(Base):
    """
    PROTOTYPE: Simulated valid document registry.
    NOT connected to any real government database.
    """
    __tablename__ = "valid_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(200))
    date_of_birth = Column(String(20))
    nationality = Column(String(10))
    issuing_country = Column(String(10))
    expiry_date = Column(String(20))
    document_type = Column(String(20), default="passport")
    status = Column(String(20), default="VALID")  # VALID, EXPIRED, CANCELLED
    is_prototype_data = Column(Boolean, default=True)


class Watchlist(Base):
    """
    PROTOTYPE: Simulated watchlist registry.
    NOT connected to any real law enforcement database.
    """
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(50), index=True)
    name = Column(String(200))
    reason = Column(String(500))
    severity = Column(String(20))  # LOW, MEDIUM, HIGH
    status = Column(String(20), default="ACTIVE")
    is_prototype_data = Column(Boolean, default=True)


class Blacklist(Base):
    """
    PROTOTYPE: Simulated blacklist registry.
    NOT connected to any real law enforcement database.
    """
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(50), index=True)
    name = Column(String(200))
    reason = Column(String(500))
    status = Column(String(20), default="ACTIVE")
    is_prototype_data = Column(Boolean, default=True)
