"""
Dashboard API routes.
GET /api/dashboard/statistics — aggregate metrics for the officer dashboard.
"""
import logging
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db.database import get_db
from app.models.models import Screening, ScreeningStatus
from app.schemas.schemas import DashboardStatistics, ScreeningListItem
from app.api.dependencies import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/statistics", response_model=DashboardStatistics)
async def get_statistics(
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """Get dashboard statistics and recent activity."""
    # Count by status
    status_counts = dict(
        db.query(Screening.status, func.count(Screening.id))
        .group_by(Screening.status)
        .all()
    )

    total = sum(status_counts.values())
    verified = status_counts.get(ScreeningStatus.VERIFIED, 0)
    suspicious = status_counts.get(ScreeningStatus.SUSPICIOUS, 0)
    high_risk = status_counts.get(ScreeningStatus.HIGH_RISK, 0)
    failed = status_counts.get(ScreeningStatus.FAILED, 0)
    pending = (
        status_counts.get(ScreeningStatus.PENDING, 0)
        + status_counts.get(ScreeningStatus.PROCESSING, 0)
    )

    # Average processing time
    avg_time = db.query(
        func.avg(Screening.processing_time_ms)
    ).filter(
        Screening.processing_time_ms.isnot(None)
    ).scalar()

    # Recent 10 screenings
    recent = db.query(Screening).order_by(
        desc(Screening.created_at)
    ).limit(10).all()

    # Risk distribution
    low_risk = db.query(func.count(Screening.id)).filter(
        Screening.risk_score <= 35
    ).scalar() or 0
    medium_risk = db.query(func.count(Screening.id)).filter(
        Screening.risk_score > 35,
        Screening.risk_score <= 65,
    ).scalar() or 0
    high_risk_count = db.query(func.count(Screening.id)).filter(
        Screening.risk_score > 65
    ).scalar() or 0

    return DashboardStatistics(
        total_screenings=total,
        verified=verified,
        suspicious=suspicious,
        high_risk=high_risk,
        failed=failed,
        pending=pending,
        average_processing_time_ms=avg_time,
        recent_screenings=recent,
        status_distribution={
            "VERIFIED": verified,
            "SUSPICIOUS": suspicious,
            "HIGH_RISK": high_risk,
            "FAILED": failed,
            "PENDING": pending,
        },
        risk_distribution={
            "low": low_risk,
            "medium": medium_risk,
            "high": high_risk_count,
        },
    )
