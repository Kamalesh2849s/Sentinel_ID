"""
Dependencies for FastAPI routes.
JWT authentication dependency for protected endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.security import decode_token
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validate JWT and return current user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if not payload:
        raise credentials_exception

    user_id: int = payload.get("user_id")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise credentials_exception

    return user


async def get_optional_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Optional auth — returns None if no token provided."""
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None
