"""
Shared plumbing for agent runs: resume lookup + the audit log.

Every orchestrator run (chat or daily) writes an AgentRun row and one
AgentAction row per tool call — the UI's activity feed reads exactly these,
so the user can always see WHAT the assistant did and WHY.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.db_models import AgentAction, AgentRun, ResumeRecord, User


def latest_ready_resume(db: Session, user_id: str) -> ResumeRecord | None:
    """The user's newest resume that is parsed AND embedded — matching-ready."""
    return (
        db.query(ResumeRecord)
        .filter(
            ResumeRecord.user_id == user_id,
            ResumeRecord.parsed_data.isnot(None),
            ResumeRecord.embedding_vector.isnot(None),
        )
        .order_by(ResumeRecord.uploaded_at.desc())
        .first()
    )


class AgentAuditLog:
    """Creates the AgentRun row and appends ordered AgentAction rows."""

    def __init__(self, db: Session, user: User, trigger: str, goal: str | None):
        self._db = db
        self._seq = 0
        self.run = AgentRun(
            run_id=str(uuid.uuid4()),
            user_id=user.user_id,
            trigger=trigger,
            goal=goal,
            status="running",
        )
        db.add(self.run)
        db.commit()

    def record(self, tool: str, tool_input: dict | None, result_summary: str) -> None:
        self._seq += 1
        self._db.add(AgentAction(
            action_id=str(uuid.uuid4()),
            run_id=self.run.run_id,
            seq=self._seq,
            tool=tool,
            tool_input=tool_input or {},
            result_summary=result_summary[:2000],  # keep rows bounded
        ))
        self._db.commit()

    def finish(self, status: str, summary: str | None) -> None:
        self.run.status = status
        self.run.summary = summary
        self.run.finished_at = datetime.now(timezone.utc)
        self._db.commit()
