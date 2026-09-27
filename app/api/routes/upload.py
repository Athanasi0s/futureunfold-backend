"""File upload endpoint for group chat media and certificate logos."""

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.core.config import PUBLIC_BASE_URL, UPLOAD_DIR
from app.core.deps import get_current_user

# Allowed MIME types mapped to (category, max_mb)
ALLOWED_MIME = {
    "image/jpeg": ("image", 10),
    "image/png": ("image", 10),
    "image/gif": ("image", 10),
    "image/webp": ("image", 10),
    "application/pdf": ("document", 25),
    "application/msword": ("document", 25),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("document", 25),
    "application/vnd.ms-excel": ("document", 25),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("document", 25),
}

# MIME type to file extension mapping
EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """
    Upload a file (image or document) and return a URL path.
    Authenticated users only.
    """
    # Extract MIME type (strip charset or boundary params)
    mime = (file.content_type or "").split(";")[0].strip()

    if mime not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime}",
        )

    # Read file content once
    contents = await file.read()

    # Validate file size
    _category, max_mb = ALLOWED_MIME[mime]
    max_bytes = max_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size for {_category} is {max_mb}MB.",
        )

    # Generate unique filename and save
    filename = f"{uuid.uuid4()}{EXT_MAP[mime]}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    # Absolute URL so callers can store the value directly into fields the mobile
    # client renders with <Image source={{ uri }}>. RN cannot load relative paths.
    return {"url": f"{PUBLIC_BASE_URL}/uploads/{filename}"}
