"""User preferences — the assistant's standing instructions.

This is where "I want AI/ML roles, remote, ₹X minimum, tailor near-misses,
email me daily" lives. The daily agent run reads exactly this row.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db_models import User, UserPreference

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferencesBody(BaseModel):
    desired_roles: list[str] = Field(
        default_factory=list,
        description='Job search queries, e.g. ["Machine Learning Engineer", "GenAI Engineer"]',
    )
    country: str = "in"
    location_contains: str | None = None
    min_salary: float | None = None
    min_match_score: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_tailor: bool = True
    daily_digest_enabled: bool = True
    notify_email: EmailStr | None = None  # unset -> account email


def _to_response(pref: UserPreference | None, user: User) -> dict:
    if pref is None:
        # Defaults for a user who never saved preferences — mirrors PreferencesBody.
        body = PreferencesBody()
        return {**body.model_dump(), "notify_email": user.email, "configured": False}
    return {
        "desired_roles": pref.desired_roles or [],
        "country": pref.country,
        "location_contains": pref.location_contains,
        "min_salary": pref.min_salary,
        "min_match_score": pref.min_match_score,
        "auto_tailor": pref.auto_tailor,
        "daily_digest_enabled": pref.daily_digest_enabled,
        "notify_email": pref.notify_email or user.email,
        "configured": True,
    }


@router.get("")
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
    return _to_response(pref, user)


@router.put("")
def save_preferences(
    body: PreferencesBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
    if pref is None:
        pref = UserPreference(user_id=user.user_id)
        db.add(pref)

    pref.desired_roles = body.desired_roles
    pref.country = body.country
    pref.location_contains = body.location_contains
    pref.min_salary = body.min_salary
    pref.min_match_score = body.min_match_score
    pref.auto_tailor = body.auto_tailor
    pref.daily_digest_enabled = body.daily_digest_enabled
    pref.notify_email = body.notify_email
    db.commit()
    db.refresh(pref)
    return _to_response(pref, user)
