"""Assistant endpoints — talk to the agent, trigger a cycle, read the audit trail."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.daily_cycle import run_daily_cycle_for_user
from app.agent.orchestrator import run_agent
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.db_models import AgentAction, AgentRun, User

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("/chat")
def chat(
    body: ChatBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One conversational turn with the orchestrator agent (may use tools)."""
    result = run_agent(db, user, body.message, trigger="chat")
    return result


@router.post("/run")
def run_cycle_now(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger the daily cycle for the current user (same as the cron)."""
    result = run_daily_cycle_for_user(db, user, trigger="manual")
    if result.get("skipped"):
        raise HTTPException(status_code=400, detail=f"Cycle skipped: {result['reason']}")
    return result


@router.get("/runs")
def list_runs(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent agent runs with their actions — the activity feed."""
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == user.user_id)
        .order_by(AgentRun.started_at.desc())
        .limit(min(limit, 50))
        .all()
    )
    run_ids = [r.run_id for r in runs]
    actions = (
        db.query(AgentAction)
        .filter(AgentAction.run_id.in_(run_ids))
        .order_by(AgentAction.seq)
        .all()
    ) if run_ids else []
    actions_by_run: dict[str, list] = {}
    for a in actions:
        actions_by_run.setdefault(a.run_id, []).append({
            "seq": a.seq, "tool": a.tool, "input": a.tool_input, "result": a.result_summary,
        })
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "trigger": r.trigger,
                "goal": r.goal,
                "status": r.status,
                "summary": r.summary,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "actions": actions_by_run.get(r.run_id, []),
            }
            for r in runs
        ]
    }
