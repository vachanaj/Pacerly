from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    height_cm: Decimal | None = Field(default=None, gt=50, le=275)
    weight_kg: Decimal | None = Field(default=None, gt=20, le=350)
    resting_hr: int | None = Field(default=None, ge=25, le=140)
    max_hr: int | None = Field(default=None, ge=100, le=240)
    baseline_pace_sec_per_km: int | None = Field(default=None, ge=120, le=1200)
    weekly_distance_goal_km: Decimal | None = Field(default=None, ge=0, le=1000)


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    display_name: str
    height_cm: Decimal | None
    weight_kg: Decimal | None
    resting_hr: int | None
    max_hr: int | None
    baseline_pace_sec_per_km: int | None
    weekly_distance_goal_km: Decimal
    profile_completed: bool
    created_at: datetime
    updated_at: datetime