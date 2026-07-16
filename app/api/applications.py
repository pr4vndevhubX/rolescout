"""Application queue — prepared packages awaiting the user's decision.

The agent PREPARES (status "prepared"); the human decides:
- approved  -> user opened the apply link intending to submit
- applied   -> user confirms it was submitted (match syncs to "applied")
- discarded -> not interested
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db_models import (
    Application,
    JobRecord,
    MatchResult,
    User,
    VALID_APPLICATION_STATUSES,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _to_response(a: Application, job: JobRecord | None) -> dict:
    return {
        "application_id": a.application_id,
        "job_id": a.job_id,
        "match_id": a.match_id,
        "title": job.title if job else "Unknown",
        "company": job.company if job else None,
        "location": job.location if job else None,
        "status": a.status,
        "tailoring": a.tailoring,
        "cover_letter": a.cover_letter,
        "apply_url": a.apply_url,
        "created_at": a.created_at,
        "applied_at": a.applied_at,
    }


@router.get("")
def list_applications(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Application).filter(Application.user_id == user.user_id)
    if status:
        query = query.filter(Application.status == status)
    apps = query.order_by(Application.created_at.desc()).all()
    jobs = {
        j.job_id: j
        for j in db.query(JobRecord).filter(JobRecord.job_id.in_([a.job_id for a in apps])).all()
    } if apps else {}
    return {"applications": [_to_response(a, jobs.get(a.job_id)) for a in apps]}


class ApplicationStatusUpdate(BaseModel):
    status: str  # approved / applied / discarded


@router.patch("/{application_id}")
def update_application(
    application_id: str,
    body: ApplicationStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.status not in VALID_APPLICATION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of {sorted(VALID_APPLICATION_STATUSES)}.",
        )
    app_row = db.query(Application).filter(
        Application.application_id == application_id,
        Application.user_id == user.user_id,
    ).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found.")

    app_row.status = body.status
    if body.status == "applied":
        app_row.applied_at = datetime.now(timezone.utc)
        # Keep the match view consistent with the application ledger.
        if app_row.match_id:
            match = db.query(MatchResult).filter(MatchResult.match_id == app_row.match_id).first()
            if match:
                match.status = "applied"
    db.commit()

    job = db.query(JobRecord).filter(JobRecord.job_id == app_row.job_id).first()
    return _to_response(app_row, job)
