"""
Screenings API routes.
Full CRUD and pipeline trigger for document screenings.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Tuple
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File,
    Form, BackgroundTasks, Query, status, Request
)
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.db.database import get_db
from app.models.models import (
    Screening, ScreeningStatus, DocumentType, User,
    IdentityVerification, FaceResult, RiskResult as RiskResultModel, AuditLog
)
from app.schemas.schemas import (
    ScreeningCreateResponse, ScreeningListItem, ScreeningDetailResponse,
    IdentityStartResponse, LivenessCheckResponse, FaceMatchResponse, IdentityVerifyResponse
)
from app.services.upload_service import upload_service
from app.services.screening.screening_service import screening_service
from app.services.face.identity_service import identity_service
from app.services.risk.risk_engine import risk_engine
from app.api.dependencies import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screenings", tags=["Screenings"])


@router.post("", response_model=ScreeningCreateResponse, status_code=201)
async def create_screening(
    background_tasks: BackgroundTasks,
    document_image: UploadFile = File(...),
    person_image: Optional[UploadFile] = File(None),
    person_frames_json: Optional[str] = Form(None),
    document_type: str = Form("passport"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Upload a document image and start screening.
    Accepts optional person photo for face verification.
    Returns screening ID immediately; processing runs in background.
    """
    # Validate document type
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        doc_type = DocumentType.PASSPORT

    # Save document image
    file_id, doc_image_path = await upload_service.save_upload(document_image, prefix="doc")

    # Save person image if provided
    person_image_path = None
    if person_image and person_image.filename:
        _, person_image_path = await upload_service.save_upload(person_image, prefix="person")

    # Parse person frames if sent
    person_frames = None
    if person_frames_json:
        try:
            import json
            person_frames = json.loads(person_frames_json)
        except Exception as e:
            logger.warning("Failed to parse person_frames_json: %s", e)

    # Create screening record
    screening = Screening(
        document_id=file_id,
        document_type=doc_type,
        status=ScreeningStatus.PENDING,
        image_path=doc_image_path,
        person_image_path=person_image_path,
        officer_id=current_user.id if current_user else None,
    )
    db.add(screening)
    db.commit()
    db.refresh(screening)

    # Run pipeline in background
    background_tasks.add_task(
        _run_pipeline_background,
        screening_id=screening.id,
        person_image_path=person_image_path,
        person_frames=person_frames,
    )

    return ScreeningCreateResponse(
        screening_id=screening.id,
        document_id=file_id,
        status=ScreeningStatus.PENDING.value,
        message="Screening created. Processing started in background.",
    )


def _run_pipeline_background(
    screening_id: int,
    person_image_path: Optional[str],
    person_frames: Optional[List[Any]] = None,
):
    """Background task: run the full screening pipeline."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        if screening:
            screening_service.run_full_pipeline(
                screening,
                db,
                person_image_path=person_image_path,
                person_frames=person_frames,
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error("Background pipeline failed for screening %d: %s", screening_id, e)
        try:
            screening = db.query(Screening).filter(Screening.id == screening_id).first()
            if screening:
                screening.status = ScreeningStatus.FAILED
                screening.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("", response_model=List[ScreeningListItem])
async def list_screenings(
    status_filter: Optional[str] = Query(None, alias="status"),
    document_type: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """List all screenings with optional filters."""
    query = db.query(Screening)

    if status_filter:
        try:
            query = query.filter(Screening.status == ScreeningStatus[status_filter.upper()])
        except KeyError:
            pass

    if document_type:
        try:
            query = query.filter(Screening.document_type == DocumentType[document_type.upper()])
        except KeyError:
            pass

    if risk_level == "low":
        query = query.filter(Screening.risk_score <= 35)
    elif risk_level == "medium":
        query = query.filter(Screening.risk_score > 35, Screening.risk_score <= 65)
    elif risk_level == "high":
        query = query.filter(Screening.risk_score > 65)

    screenings = query.order_by(desc(Screening.created_at)).offset(offset).limit(limit).all()
    return screenings


@router.get("/{screening_id}")
async def get_screening(
    screening_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get complete screening details including all analysis results."""
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail=f"Screening {screening_id} not found")

    # Build base response using Pydantic
    response = ScreeningDetailResponse.model_validate(screening)
    result = response.model_dump()

    # ── Enrich MRZ data by re-parsing raw_mrz if available ───────────────────
    mrz_rec = screening.mrz_result
    if mrz_rec and mrz_rec.raw_mrz:
        from app.services.mrz.mrz_parser import mrz_parser as _mrz_parser
        try:
            parsed = _mrz_parser.parse(mrz_rec.raw_mrz)
            enriched_mrz = parsed.to_dict()
            # Merge DB consistency data into mrz result if present
            result["mrz_result"] = enriched_mrz
        except Exception as e:
            logger.warning("MRZ re-parse failed for enrichment: %s", e)
    elif mrz_rec:
        # Ensure mrz_status is always present
        if result.get("mrz_result"):
            result["mrz_result"]["mrz_status"] = (
                "NOT_DETECTED" if not mrz_rec.mrz_detected else
                ("VALID" if mrz_rec.check_digit_valid else "CHECK_DIGIT_FAILURE")
            )

    doc = screening.extracted_document
    mrz = screening.mrz_result
    if mrz and mrz.mrz_detected and doc:
        from app.services.screening.screening_service import screening_service as _ss
        ocr_data = {
            "name_ocr": doc.name_ocr,
            "full_name": doc.full_name,
            "document_number": doc.document_number,
            "date_of_birth": doc.date_of_birth,
            "expiry_date": doc.expiry_date,
            "nationality": doc.nationality,
            "nationality_code": doc.nationality_code,
        }
        mrz_data_for_cons = result.get("mrz_result") or {}
        consistency = _ss._compute_mrz_ocr_consistency(mrz_data_for_cons, ocr_data)
        if result.get("mrz_result"):
            result["mrz_result"]["consistency"] = consistency

    if result.get("extracted_document") and doc:
        ext = result["extracted_document"]
        ext["nationality_code"] = doc.nationality_code or (doc.nationality if len(doc.nationality or "") == 3 else None)
        ext["issuing_country_code"] = doc.issuing_country_code or (doc.issuing_country if len(doc.issuing_country or "") == 3 else None)
        ext["date_of_issue"] = doc.date_of_issue or doc.issue_date
        ext["date_of_issue_source"] = doc.date_of_issue_source or ("OCR/VIZ" if ext["date_of_issue"] else "Not detected")
        ext["name_ocr"] = doc.name_ocr
        ext["name_mrz"] = doc.name_mrz
        ext["name_source"] = doc.name_source or ("MRZ + OCR" if (doc.name_consistency in ("MATCH", "PARTIAL_MATCH")) else ("MRZ" if doc.name_mrz else ("OCR" if doc.name_ocr else None)))
        ext["name_consistency"] = doc.name_consistency
        ext["name_confidence"] = doc.name_confidence

    # ── Separate Risk Status and Risk Score ───────────────────────────────────
    risk_rec = screening.risk_result
    risk_status = "pending"
    risk_score = None
    risk_level = None
    reasons = []
    failure_reason = None

    if risk_rec:
        risk_status = risk_rec.risk_status or ("completed" if risk_rec.risk_score is not None else "pending")
        risk_score = risk_rec.risk_score
        risk_level = risk_rec.risk_level
        reasons = risk_rec.reasons or []
        failure_reason = risk_rec.failure_reason
    elif screening.status in (ScreeningStatus.PENDING, ScreeningStatus.PROCESSING):
        risk_status = "pending"
    elif screening.status == ScreeningStatus.FAILED:
        risk_status = "failed"

    # Enforce: do not use score=0 as placeholder for not calculated
    if risk_status != "completed":
        risk_score = None

    result["risk_score"] = risk_score
    result["risk"] = {
        "status": risk_status,
        "score": risk_score,
        "level": risk_level,
        "reasons": reasons,
        "failure_reason": failure_reason,
    }
    if result.get("risk_result"):
        result["risk_result"]["risk_score"] = risk_score
        result["risk_result"]["risk_status"] = risk_status
        result["risk_result"]["risk_level"] = risk_level
        result["risk_result"]["failure_reason"] = failure_reason

    return result


@router.post("/{screening_id}/reprocess", status_code=202)
async def reprocess_screening(
    screening_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Trigger re-processing of an existing screening."""
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    if not screening.image_path:
        raise HTTPException(status_code=400, detail="No document image found for this screening")

    screening.status = ScreeningStatus.PENDING
    db.commit()

    background_tasks.add_task(
        _run_pipeline_background,
        screening_id=screening.id,
        person_image_path=screening.person_image_path,
    )

    return {"message": "Reprocessing started", "screening_id": screening_id}


# ─── Identity Verification Endpoints ──────────────────────────────────────────

async def _extract_frames_from_request(
    request: Request,
    uploaded_files: Optional[List[UploadFile]] = None,
) -> Tuple[List[Any], bool]:
    """Extract frames and upload flag from request (supports JSON and Multipart)."""
    frames = []
    is_upload = False

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            frames = body.get("frames", [])
            is_upload = body.get("is_upload", False)
            return frames, is_upload
        except Exception:
            pass

    if uploaded_files:
        for f in uploaded_files:
            content = await f.read()
            if content:
                frames.append(content)

    return frames, is_upload


@router.post("/{screening_id}/identity/start", response_model=IdentityStartResponse)
async def start_identity_verification(
    screening_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Initialize identity verification stage.
    Detects face and generates embedding from uploaded document.
    """
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    if not screening.image_path:
        raise HTTPException(status_code=400, detail="No document image found for this screening")

    doc_face_res = identity_service.extract_document_face(screening.image_path)
    detected = doc_face_res.get("document_face_detected", False)
    quality = doc_face_res.get("document_face_quality", 0.0)
    embedding_avail = doc_face_res.get("document_face_embedding_available", False)

    msg = (
        "Document face detected and embedding generated. Ready for person camera frames."
        if detected else
        "No face detected in document. Document image must contain a clear photograph."
    )

    return IdentityStartResponse(
        screening_id=screening.id,
        document_face_detected=detected,
        document_face_quality=quality,
        document_face_embedding_available=embedding_avail,
        status="READY" if detected else "NO_FACE",
        message=msg,
    )


@router.post("/{screening_id}/identity/liveness", response_model=LivenessCheckResponse)
async def check_identity_liveness(
    screening_id: int,
    request: Request,
    frames: Optional[List[UploadFile]] = File(None),
    is_upload: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Modular Liveness Detection API.
    Performs temporal motion, frame analysis, and eye/blink verification across camera frames.
    """
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    frame_list, single_upload_flag = await _extract_frames_from_request(request, frames)
    if is_upload:
        single_upload_flag = True

    liveness_decision = identity_service.verify_liveness(
        frames=frame_list,
        is_single_image_upload=single_upload_flag,
    )

    return LivenessCheckResponse(
        screening_id=screening.id,
        liveness_status=liveness_decision.status,
        confidence=liveness_decision.confidence,
        frames_count=liveness_decision.frames_analyzed,
        details=liveness_decision.details,
        failure_reason=liveness_decision.failure_reason,
    )


@router.post("/{screening_id}/identity/face", response_model=FaceMatchResponse)
async def check_identity_face(
    screening_id: int,
    request: Request,
    frames: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Face matching API.
    Extracts person face embedding from best frame and compares with document face.
    """
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    if not screening.image_path:
        raise HTTPException(status_code=400, detail="No document image found")

    doc_face_res = identity_service.extract_document_face(screening.image_path)
    doc_embedding = doc_face_res.get("embedding")

    frame_list, _ = await _extract_frames_from_request(request, frames)

    person_face_res = identity_service.verify_person_face(frame_list, doc_embedding)

    return FaceMatchResponse(
        screening_id=screening.id,
        person_face_detected=person_face_res.get("person_face_detected", False),
        similarity=person_face_res.get("similarity", 0.0),
        match=person_face_res.get("match", False),
        threshold=person_face_res.get("threshold", settings.FACE_SIMILARITY_THRESHOLD),
        confidence=person_face_res.get("similarity", 0.0),
    )


@router.post("/{screening_id}/identity/verify", response_model=IdentityVerifyResponse)
async def verify_identity_endpoint(
    screening_id: int,
    request: Request,
    frames: Optional[List[UploadFile]] = File(None),
    is_upload: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Full Identity Verification Stage.
    Requires:
      Liveness = PASS
      AND Document Face = detected
      AND Person Face = detected
      AND Face Similarity >= configured threshold
    Updates risk score, screening status, and database record.
    """
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    if not screening.image_path:
        raise HTTPException(status_code=400, detail="No document image found")

    frame_list, single_upload_flag = await _extract_frames_from_request(request, frames)
    if is_upload:
        single_upload_flag = True

    # Run complete identity verification
    identity_res = identity_service.verify_identity(
        doc_image_path=screening.image_path,
        person_frames=frame_list,
        is_single_image_upload=single_upload_flag,
    )

    # Persist in DB
    identity_service.save_identity_result(db, screening.id, identity_res)

    # Recalculate Risk Result with the new identity verification output
    mrz_data = screening.mrz_result.__dict__ if screening.mrz_result else {}
    tamper_data = screening.tamper_result.__dict__ if screening.tamper_result else {}
    validations = [v.__dict__ for v in screening.validation_results] if screening.validation_results else []
    ocr_data = screening.extracted_document.__dict__ if screening.extracted_document else {}

    face_data = {
        "face_detected_document": identity_res["document_face"]["detected"],
        "face_detected_person": identity_res["person_face"]["detected"],
        "similarity": identity_res["face_match"]["similarity"],
        "match": (identity_res["face_match"]["status"] == "PASS"),
        "confidence": identity_res["face_match"]["similarity"],
        "liveness_status": identity_res["liveness"]["status"],
        "failure_reason": identity_res.get("failure_reason"),
    }

    database_data = {}
    for c in validations:
        if c.get("check_name") == "watchlist":
            database_data["watchlist_match"] = (c.get("status") == "FAIL")
        if c.get("check_name") == "blacklist":
            database_data["blacklist_match"] = (c.get("status") == "FAIL")

    risk_result = risk_engine.calculate(
        mrz_result=mrz_data,
        database_result=database_data,
        tamper_result=tamper_data,
        face_result=face_data,
        validation_checks=validations,
        identity_result=identity_res,
        ocr_data=ocr_data,
        require_signals=True,
    )

    # Save risk result
    from app.models.models import ScreeningStatus as SS
    status_enum = SS[risk_result.status] if (risk_result.status and risk_result.status in SS.__members__) else SS.SUSPICIOUS
    existing_risk = screening.risk_result
    if existing_risk:
        existing_risk.risk_score = risk_result.risk_score
        existing_risk.risk_status = risk_result.risk_status
        existing_risk.risk_level = risk_result.risk_level
        existing_risk.failure_reason = risk_result.failure_reason
        existing_risk.calculated_at = risk_result.calculated_at or datetime.utcnow()
        existing_risk.status = status_enum
        existing_risk.face_risk = risk_result.face_risk
        existing_risk.reasons = [r.to_dict() if hasattr(r, "to_dict") else r for r in risk_result.reasons]
        existing_risk.recommendation = risk_result.recommendation
        existing_risk.weights_used = risk_result.weights_used
    else:
        new_risk = RiskResultModel(
            screening_id=screening.id,
            risk_score=risk_result.risk_score,
            risk_status=risk_result.risk_status,
            risk_level=risk_result.risk_level,
            failure_reason=risk_result.failure_reason,
            calculated_at=risk_result.calculated_at or datetime.utcnow(),
            status=status_enum,
            mrz_risk=risk_result.mrz_risk,
            database_risk=risk_result.database_risk,
            tamper_risk=risk_result.tamper_risk,
            face_risk=risk_result.face_risk,
            consistency_risk=risk_result.consistency_risk,
            reasons=[r.to_dict() if hasattr(r, "to_dict") else r for r in risk_result.reasons],
            recommendation=risk_result.recommendation,
            weights_used=risk_result.weights_used,
        )
        db.add(new_risk)

    screening.status = status_enum
    screening.risk_score = risk_result.risk_score
    if risk_result.risk_status == "completed":
        screening.completed_at = datetime.utcnow()

    # Audit log
    audit = AuditLog(
        screening_id=screening.id,
        action="IDENTITY_VERIFICATION",
        status="SUCCESS" if identity_res.get("status") == "PASS" else "FAILED",
        action_metadata={
            "identity_status": identity_res.get("status"),
            "liveness": identity_res.get("liveness", {}).get("status"),
            "face_match": identity_res.get("face_match", {}).get("status"),
            "similarity": identity_res.get("face_match", {}).get("similarity"),
        },
        error_message=identity_res.get("failure_reason"),
    )
    db.add(audit)
    db.commit()

    return IdentityVerifyResponse(
        screening_id=screening.id,
        identity_verification=identity_res,
        screening_status=screening.status.value,
        risk_score=screening.risk_score,
        message="Identity verification completed",
    )


@router.get("/{screening_id}/identity")
async def get_identity_verification(
    screening_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get current identity verification state and breakdown for screening."""
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    id_rec = screening.identity_verification

    if id_rec:
        return {
            "screening_id": screening.id,
            "identity_verification": {
                "status": id_rec.identity_status,
                "liveness": id_rec.liveness,
                "document_face": id_rec.document_face,
                "person_face": id_rec.person_face,
                "face_match": id_rec.face_match,
                "failure_reason": id_rec.failure_reason,
            },
            "created_at": id_rec.created_at,
            "completed_at": id_rec.completed_at,
        }

    # Not yet run: extract document face so client knows document readiness
    doc_face = identity_service.extract_document_face(screening.image_path) if screening.image_path else {}
    return {
        "screening_id": screening.id,
        "identity_verification": {
            "status": "INCOMPLETE",
            "reason": "Person verification is required",
            "failure_reason": "Person verification is required",
            "liveness": {"status": "INCOMPLETE", "confidence": 0.0},
            "document_face": {
                "detected": doc_face.get("document_face_detected", False),
                "quality": doc_face.get("document_face_quality", 0.0),
                "embedding_available": doc_face.get("document_face_embedding_available", False),
            },
            "person_face": {"detected": False},
            "face_match": {"status": "NOT_EVALUATED", "similarity": 0.0, "threshold": settings.FACE_SIMILARITY_THRESHOLD},
        },
    }
