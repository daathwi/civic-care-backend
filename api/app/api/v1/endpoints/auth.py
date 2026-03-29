from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db.database import get_db
from app.models.models import RefreshToken, User, Ward, WorkerProfile, Zone
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.api.deps import get_current_user, require_manager, require_staff
from starlette.concurrency import run_in_threadpool
from app.services.delhi_ward_lookup import get_ward_from_location
from app.services.cis_service import fetch_latest_cis_snapshots_for_users

router = APIRouter(prefix="/auth", tags=["auth"])


async def _user_out_with_cis(
    db: AsyncSession,
    user: User,
    *,
    cis_map: dict | None = None,
) -> UserOut:
    """Merge `users.cis_score` (authoritative after Update CIS) with latest snapshot metadata."""
    base = UserOut.model_validate(user)
    role_v = getattr(user.role, "value", user.role)
    if role_v != "citizen":
        return base
    if cis_map is None:
        cis_map = await fetch_latest_cis_snapshots_for_users(db, [user.id])
    snap = cis_map.get(user.id)
    score = float(user.cis_score) if user.cis_score is not None else None
    if score is None and snap is not None and snap.total_score is not None:
        score = float(snap.total_score)
    upd: dict = {}
    if score is not None:
        upd["cis_total_score"] = score
    if snap is not None:
        upd.update(
            {
                "cis_week_start": snap.week_start,
                "cis_week_end": snap.week_end,
                "cis_computed_at": snap.computed_at,
            }
        )
    if upd:
        return base.model_copy(update=upd)
    return base


def _build_auth_response(user: User, access: str, refresh: str) -> AuthResponse:
    return AuthResponse(
        user=UserOut.model_validate(user),
        tokens=TokenResponse(access_token=access, refresh_token=refresh),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join the community",
    description="Create your own citizen account. No previous account is needed. This will give you access to report issues and track them.",
    operation_id="registerAccount",
    response_description="User and access/refresh tokens.",
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already registered")

    ward_display: str | None = None
    zone_display: str | None = None

    if body.zone_id is not None:
        zone_row = await db.execute(select(Zone).where(Zone.id == body.zone_id))
        zone_obj = zone_row.scalar_one_or_none()
        if zone_obj:
            zone_display = zone_obj.name
    if body.ward_id is not None:
        ward_row = await db.execute(select(Ward).where(Ward.id == body.ward_id))
        ward_obj = ward_row.scalar_one_or_none()
        if ward_obj:
            ward_display = ward_obj.name

    if not ward_display and not zone_display and body.lat is not None and body.lng is not None:
        loc_info = await run_in_threadpool(get_ward_from_location, body.lat, body.lng)
        if loc_info:
            ward_display = loc_info.get("ward_display") or None
            zone_display = loc_info.get("zone_display") or None

    user = User(
        name=body.name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        password_hash=get_password_hash(body.password),
        role="citizen",
        ward=ward_display,
        ward_id=body.ward_id,
        zone=zone_display,
        zone_id=body.zone_id,
    )
    db.add(user)
    await db.flush()

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token=refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    # Refetch with worker_profile loaded so UserOut.model_validate doesn't trigger lazy load
    result = await db.execute(
        select(User)
        .options(
                selectinload(User.worker_profile).options(
                    selectinload(WorkerProfile.department),
                    selectinload(WorkerProfile.ward),
                )
            )
        .where(User.id == user.id)
    )
    user = result.scalar_one()
    return _build_auth_response(user, access, refresh)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in to your account",
    description="Use this to login to your dashboard. Citizens use their phone number, while staff can use their ID or phone.",
    operation_id="loginToAccount",
    response_description="User and access/refresh tokens.",
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = None
    invalid_msg = "Invalid credentials"
    if body.user_id is not None:
        raw = body.user_id.strip()
        # Try by UUID first, then by phone (department staff can use either)
        try:
            from uuid import UUID
            uid = UUID(raw)
            result = await db.execute(
                select(User)
                .options(
                selectinload(User.worker_profile).options(
                    selectinload(WorkerProfile.department),
                    selectinload(WorkerProfile.ward),
                )
            )
                .where(User.id == uid)
            )
            user = result.scalar_one_or_none()
        except (ValueError, TypeError):
            pass
        if user is None:
            result = await db.execute(
                select(User)
                .options(
                selectinload(User.worker_profile).options(
                    selectinload(WorkerProfile.department),
                    selectinload(WorkerProfile.ward),
                )
            )
                .where(User.phone == raw)
            )
            user = result.scalar_one_or_none()
        invalid_msg = "Invalid user id / phone or password"
    else:
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.worker_profile).options(
                    selectinload(WorkerProfile.department),
                    selectinload(WorkerProfile.ward),
                )
            )
            .where(User.phone == body.phone)
        )
        user = result.scalar_one_or_none()
        invalid_msg = "Invalid phone or password"

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, invalid_msg)

    # Check role in user object: citizens are not allowed in department portal (staff-only)
    role = getattr(user.role, "value", user.role) if hasattr(user.role, "value") else str(user.role)
    if role == "citizen" and body.user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Department login is for staff only. Use the Citizen tab and log in with your phone number.",
        )

    if body.department and user.worker_profile:
        if user.worker_profile.department_id != body.department:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Department mismatch")

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token=refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    return _build_auth_response(user, access, refresh)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Keep your session alive",
    description="Use this to get a new access token when your current one is about to expire. It keeps you logged in without asking for password again.",
    operation_id="refreshSessionToken",
    response_description="New access and refresh tokens.",
)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(body.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == body.refresh_token,
            RefreshToken.user_id == user_id,
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token not found")
    if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    await db.delete(stored)

    new_access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token=new_refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.get(
    "/me",
    response_model=UserOut,
    summary="See your profile details",
    description="Use this to see who is currently logged in and what permissions they have.",
    operation_id="getCurrentUserDashboard",
    response_description="Current user profile.",
)
async def get_me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get(
    "/users",
    summary="List users by role",
    description="List citizens or staff. Admin/manager only.",
    operation_id="listUsers",
)
async def list_users(
    role: str | None = None,
    skip: int = 0,
    limit: int = 50,
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count(User.id))
    if role:
        count_q = count_q.where(User.role == role)
    total = (await db.scalar(count_q)) or 0
    q = (
        select(User)
        .options(
            selectinload(User.worker_profile).options(
                selectinload(WorkerProfile.department),
                selectinload(WorkerProfile.ward),
            )
        )
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if role:
        q = q.where(User.role == role)
    result = await db.execute(q)
    users = result.scalars().unique().all()
    if role == "citizen" and users:
        cis_map = await fetch_latest_cis_snapshots_for_users(db, [u.id for u in users])
        items = [await _user_out_with_cis(db, u, cis_map=cis_map) for u in users]
        return {"items": items, "total": total}
    return {"items": [UserOut.model_validate(u) for u in users], "total": total}


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Look up a specific user",
    description="Use this to find details about a specific person in the system by their unique ID.",
    operation_id="getUserProfileDetails",
    response_description="User profile.",
)
async def get_user_by_id(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = getattr(current_user.role, "value", current_user.role)
    if current_user.id != user_id and role not in ("admin", "fieldManager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to view this user")
    result = await db.execute(
        select(User)
        .options(
                selectinload(User.worker_profile).options(
                    selectinload(WorkerProfile.department),
                    selectinload(WorkerProfile.ward),
                )
            )
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return await _user_out_with_cis(db, user)
