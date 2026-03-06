from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app.api.deps import get_current_user
from app.models.models import User

router = APIRouter(prefix="/upload", tags=["upload"])

PHOTOS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "photos"
GRIEVANCE_PHOTOS_DIR = PHOTOS_DIR / "grievances"
RESOLUTION_PHOTOS_DIR = PHOTOS_DIR / "resolutions"

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "assets"
AUDIO_DIR = ASSETS_DIR / "audio"

ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".3gp", ".ogg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _ensure_dirs():
    GRIEVANCE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOLUTION_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/grievance-photo",
    status_code=status.HTTP_201_CREATED,
    summary="Upload grievance photo",
    description="Upload a photo for a grievance. Returns the URL to reference in grievance creation.",
)
async def upload_grievance_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    return await _save_file(file, GRIEVANCE_PHOTOS_DIR, "photos/grievances", ALLOWED_PHOTO_EXTENSIONS)


@router.post(
    "/resolution-photo",
    status_code=status.HTTP_201_CREATED,
    summary="Upload resolution proof photo",
    description="Upload a resolution proof photo. Returns the URL to reference in grievance update.",
)
async def upload_resolution_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    return await _save_file(file, RESOLUTION_PHOTOS_DIR, "photos/resolutions", ALLOWED_PHOTO_EXTENSIONS)


@router.post(
    "/grievance-audio",
    status_code=status.HTTP_201_CREATED,
    summary="Upload grievance audio",
    description="Upload a voice recording for a grievance. Returns the URL to reference in grievance creation.",
)
async def upload_grievance_audio(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    return await _save_file(file, AUDIO_DIR, "assets/audio", ALLOWED_AUDIO_EXTENSIONS)


async def _save_file(file: UploadFile, directory: Path, url_prefix: str, allowed_exts: set) -> dict:
    _ensure_dirs()

    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File type {ext} not allowed. Use: {', '.join(allowed_exts)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 10MB)")

    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = directory / unique_name
    file_path.write_bytes(content)

    url = f"/{url_prefix}/{unique_name}"
    return {"url": url, "filename": unique_name}
