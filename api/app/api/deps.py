from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.database import get_db
from app.models.models import User, WorkerProfile

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return await _decode_user(creds.credentials, db)


async def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return current user if valid Bearer token present, else None."""
    if creds is None:
        return None
    try:
        return await _decode_user(creds.credentials, db)
    except HTTPException:
        return None


async def _decode_user(token: str, db: AsyncSession) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate token")

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.worker_profile).options(
                selectinload(WorkerProfile.department),
                selectinload(WorkerProfile.ward),
            )
        )
        .where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def require_citizen(user: User = Depends(get_current_user)) -> User:
    if user.role != "citizen":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Citizen role required")
    return user


def _role_str(user: User) -> str:
    """Normalize role for comparison (DB may return enum or string)."""
    r = getattr(user, "role", None)
    if r is None:
        return ""
    return getattr(r, "value", r) if hasattr(r, "value") else str(r)


async def require_manager(user: User = Depends(get_current_user)) -> User:
    """Field Manager or Admin can assign workers, create resources, etc."""
    if _role_str(user) not in ("fieldManager", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Field Manager or Admin role required")
    return user


async def require_can_update_grievance(user: User = Depends(get_current_user)) -> User:
    """Only Field Assistant or Admin can update grievance (not Field Manager)."""
    if _role_str(user) not in ("fieldAssistant", "admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Field Assistant or Admin can update grievance",
        )
    return user


async def require_worker(user: User = Depends(get_current_user)) -> User:
    if _role_str(user) != "fieldAssistant":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Field Assistant role required")
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Staff: Field Manager, Field Assistant, or Admin."""
    if _role_str(user) not in ("fieldManager", "fieldAssistant", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff role required")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if _role_str(user) != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
