"""
SentinelID Backend Configuration
All configurable values loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "SentinelID"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Database
    DATABASE_URL: str = "sqlite:///./sentinelid.db"

    # Upload Configuration
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"

    # OCR Engine
    OCR_ENGINE: str = "paddleocr"  # paddleocr or tesseract

    # Risk Engine Weights
    RISK_WEIGHT_MRZ: int = 20
    RISK_WEIGHT_DATABASE: int = 20
    RISK_WEIGHT_TAMPER: int = 25
    RISK_WEIGHT_FACE: int = 25
    RISK_WEIGHT_CONSISTENCY: int = 10

    # Risk Thresholds (0-100 scale)
    RISK_THRESHOLD_VERIFIED: int = 35
    RISK_THRESHOLD_SUSPICIOUS: int = 65

    # Face Verification & Liveness
    FACE_SIMILARITY_THRESHOLD: float = 0.6
    LIVENESS_MIN_FRAMES: int = 5
    RISK_WEIGHT_IDENTITY: int = 25

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # Processing
    PROCESSING_TIMEOUT_SECONDS: int = 60

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def risk_weights(self) -> dict:
        return {
            "mrz": self.RISK_WEIGHT_MRZ,
            "database": self.RISK_WEIGHT_DATABASE,
            "tamper": self.RISK_WEIGHT_TAMPER,
            "face": self.RISK_WEIGHT_FACE,
            "consistency": self.RISK_WEIGHT_CONSISTENCY,
        }

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
