"""
Authentication API routes.
POST /api/auth/login — validate credentials, return JWT token.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User
from app.core.security import verify_password, create_access_token
from app.schemas.schemas import LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate an officer and return a JWT access token.
    """
    user = db.query(User).filter(
        User.username == request.username,
        User.is_active == True,
    ).first()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token(data={
        "sub": user.username,
        "user_id": user.id,
        "role": user.role.value,
    })

    logger.info("Login successful: %s (role=%s)", user.username, user.role.value)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        role=user.role.value,
        full_name=user.full_name,
    )
