from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, engine, get_db
from app.models import UserProfile
from app.schemas import UserProfileResponse, UserProfileUpdate
from shared.auth import AuthenticatedUser, get_current_user, require_role


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Pacerly User Service",
    version="1.0.0",
    openapi_url="/user/openapi.json",
    docs_url="/user/docs",
    lifespan=lifespan,
)


def _to_response(profile: UserProfile) -> UserProfileResponse:
    completed = all(
        v is not None
        for v in (
            profile.height_cm,
            profile.weight_kg,
            profile.resting_hr,
            profile.max_hr,
            profile.baseline_pace_sec_per_km,
        )
    )
    return UserProfileResponse(
        user_id=profile.user_id,
        email=profile.email,
        display_name=profile.display_name,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        resting_hr=profile.resting_hr,
        max_hr=profile.max_hr,
        baseline_pace_sec_per_km=profile.baseline_pace_sec_per_km,
        weekly_distance_goal_km=profile.weekly_distance_goal_km,
        profile_completed=completed,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _get_or_provision_profile(
    current_user: AuthenticatedUser, db: AsyncSession
) -> UserProfile:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(
            user_id=current_user.user_id,
            email=current_user.email,
            display_name=current_user.display_name,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@app.get("/user/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "user-service"}


@app.get("/user/me", response_model=UserProfileResponse, tags=["Profile"])
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_provision_profile(current_user, db)
    return _to_response(profile)


@app.put("/user/me", response_model=UserProfileResponse, tags=["Profile"])
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_provision_profile(current_user, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return _to_response(profile)


@app.delete("/user/me", status_code=status.HTTP_204_NO_CONTENT, tags=["Profile"])
async def delete_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        await db.delete(profile)
        await db.commit()


@app.get(
    "/user/admin/profiles",
    response_model=list[UserProfileResponse],
    tags=["Admin"],
)
async def list_all_profiles(
    _admin: AuthenticatedUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).order_by(UserProfile.created_at.desc()))
    return [_to_response(p) for p in result.scalars().all()]