"""
Upload service: validates and stores document image uploads.
Handles file type checking, size limits, safe naming, and storage.
"""
import os
import uuid
import logging
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile, HTTPException
from PIL import Image
import io

from app.core.config import settings

logger = logging.getLogger(__name__)


class UploadService:
    """
    Secure document image upload handler.
    Validates format, size, and content before storage.
    """

    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile, prefix: str = "doc") -> Tuple[str, str]:
        """
        Validate and save an uploaded image file.
        Returns (file_id, saved_path).
        """
        # Validate content type
        self._validate_content_type(file.content_type, file.filename)

        # Read file content
        content = await file.read()

        # Validate file size
        self._validate_size(len(content))

        # Validate that it's actually an image
        self._validate_image_content(content)

        # Generate safe filename
        file_id = str(uuid.uuid4())
        extension = self._get_safe_extension(file.filename)
        safe_filename = f"{prefix}_{file_id}{extension}"
        save_path = self.upload_dir / safe_filename

        # Write to disk
        with open(save_path, "wb") as f:
            f.write(content)

        logger.info("Saved upload: %s (%d bytes)", safe_filename, len(content))
        return file_id, str(save_path)

    def _validate_content_type(self, content_type: str, filename: str):
        """Validate MIME type and file extension."""
        allowed_mimes = {
            "image/jpeg", "image/jpg", "image/png", "image/webp"
        }
        if content_type and content_type.lower() not in allowed_mimes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Allowed: JPG, PNG, WEBP"
            )

        if filename:
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext not in settings.allowed_extensions_list:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported extension: .{ext}. Allowed: {settings.ALLOWED_EXTENSIONS}"
                )

    def _validate_size(self, size_bytes: int):
        """Validate file does not exceed maximum size."""
        if size_bytes > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {size_bytes / 1024 / 1024:.1f}MB. "
                       f"Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB"
            )
        if size_bytes < 100:
            raise HTTPException(
                status_code=400,
                detail="File too small to be a valid image"
            )

    def _validate_image_content(self, content: bytes):
        """Validate that file content is actually a valid image."""
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image content: {str(e)}"
            )

    def _get_safe_extension(self, filename: str) -> str:
        """Extract and sanitize file extension."""
        if not filename:
            return ".jpg"
        ext = Path(filename).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            return ext
        return ".jpg"

    def get_image_path(self, filename: str) -> str:
        """Get the full path to a stored image."""
        return str(self.upload_dir / filename)

    def delete_image(self, image_path: str):
        """Delete a stored image file."""
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logger.warning("Could not delete image %s: %s", image_path, e)


upload_service = UploadService()
