"""
The daily autonomous run — deterministic by design.

The chat path uses the LangGraph orchestrator (the LLM decides what to do);
the DAILY path is a fixed, auditable pipeline: same steps every morning, LLM
spend only where it buys something (per-job fit analysis inside ranking, and
tailoring for at most MAX_TAILOR_PER_RUN near-miss jobs). Both paths write
the same AgentRun/AgentAction audit trail.

Per user with daily_digest_enabled and a matching-ready resume:
  1. Ingest every desired-role query from all sources; embed new jobs.
  2. Generate matches (hard filters from preferences applied).
  3. Split into strong fits (blended >= min_match_score) and near-misses
     (good vector similarity but blended below threshold).
  4. Auto-tailor near-misses (if auto_tailor) — truthful suggestions only.
  5. Prepare application packages for strong fits (dedup by (user, job)).
  6. Email ONE digest with everything new; log to notification_log so no
     job is ever notified twice.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.agent.context import AgentAuditLog, latest_ready_resume
from app.models.db_models import (
    Application,
    JobRecord,
    NotificationLog,
    User,
    UserPreference,
)
from app.models.parsed_resume import ParsedResume
from app.services import notification_service
from app.services.job_ingestion import embed_pending_jobs, ingest_from_sources
from app.services.match_repository import save_match_results
from app.services.matching.ranker import rank_jobs
from app.services.matching.retrieval import get_shortlist
from app.services.resume_text_builder import build_resume_summary_text
from app.services.tailoring_service import TailoringError, tailor_resume_for_job

logger = logging.getLogger(__name__)

NEAR_MISS_VECTOR_FLOOR = 0.40   # semantically close enough to be worth tailoring
MAX_TAILOR_PER_RUN = 3          # LLM cost guard
MAX_DIGEST_JOBS = 10


def classify_matches(ranked: list[dict], min_match_score: float) -> tuple[list[dict], list[dict]]:
    """Splits ranked matches into (strong_fits, near_misses). Pure — unit-tested."""
    strong, near = [], []
    for m in ranked:
        if m["blended_score"] >= min_match_score:
            strong.append(m)
        elif m["vector_similarity"] >= NEAR_MISS_VECTOR_FLOOR:
            near.append(m)
    return strong, near


def _unnotified(db: Session, user_id: str, matches: list[dict]) -> list[dict]:
    if not matches:
        return []
    seen = {
        row.job_id
        for row in db.query(NotificationLog.job_id)
        .filter(NotificationLog.user_id == user_id)
        .all()
    }
    return [m for m in matches if m["job_id"] not in seen]


def run_daily_cycle_for_user(db: Session, user: User, *, trigger: str = "daily") -> dict:
    """Runs the full cycle for one user. Returns a summary dict (also stored on the AgentRun)."""
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
    if not pref or not pref.daily_digest_enabled or not (pref.desired_roles or []):
        return {"skipped": True, "reason": "no preferences / digest disabled / no desired roles"}

    resume = latest_ready_resume(db, user.user_id)
    if not resume:
        return {"skipped": True, "reason": "no parsed+embedded resume"}

    audit = AgentAuditLog(db, user, trigger=trigger, goal="Daily job hunt cycle")
    try:
        # 1. Scout: ingest every desired role, then embed whatever is new.
        total_new = 0
        for role in pref.desired_roles:
            result = ingest_from_sources(db, role, country=pref.country)
            total_new += result["total_ingested"]
            audit.record("search_jobs", {"query": role, "country": pref.country},
                         f"{result['total_ingested']} ingested, {result['total_deduplicated']} deduped")
        embedded = embed_pending_jobs(db)
        audit.record("embed_new_jobs", {}, f"{embedded} jobs embedded")

        # 2. Evaluator: match against the resume with the user's hard filters.
        parsed = ParsedResume(**resume.parsed_data)
        summary_text = build_resume_summary_text(parsed)
        shortlist = get_shortlist(db, list(resume.embedding_vector), top_n=40)
        ranked = rank_jobs(
            shortlist, parsed,
            resume_summary_text=summary_text,
            resume_raw_text=resume.extracted_text or "",
            location_contains=pref.location_contains,
            min_salary=int(pref.min_salary) if pref.min_salary else None,
        )
        records = save_match_results(db, resume.resume_id, ranked)
        match_id_by_job = {r.job_id: r.match_id for r in records}
        audit.record("generate_matches", {}, f"{len(ranked)} matches generated")

        # 3. Classify, and drop anything already notified or already applied to.
        strong, near = classify_matches(ranked, pref.min_match_score)
        applied_jobs = {
            a.job_id
            for a in db.query(Application.job_id).filter(Application.user_id == user.user_id).all()
        }
        strong = [m for m in _unnotified(db, user.user_id, strong) if m["job_id"] not in applied_jobs]
        near = [m for m in _unnotified(db, user.user_id, near) if m["job_id"] not in applied_jobs]
        audit.record("classify_matches", {"min_score": pref.min_match_score},
                     f"{len(strong)} strong fits, {len(near)} near-misses (new only)")

        # 4. Tailor: adapt the resume for the closest near-misses.
        tailored_count = 0
        if pref.auto_tailor:
            for m in near[:MAX_TAILOR_PER_RUN]:
                job = db.query(JobRecord).filter(JobRecord.job_id == m["job_id"]).first()
                try:
                    m["tailoring"] = tailor_resume_for_job(
                        resume_summary=summary_text,
                        job_title=m["title"],
                        company=m.get("company"),
                        job_description=(job.description if job else "") or "",
                        missing_skills=m.get("missing_skills") or [],
                        ats_missing_keywords=m.get("ats_missing_keywords") or [],
                    )
                    tailored_count += 1
                    audit.record("tailor_resume", {"job": m["title"]}, "tailoring suggestions generated")
                except (TailoringError, Exception) as e:  # noqa: BLE001 — cycle must survive
                    audit.record("tailor_resume", {"job": m["title"]}, f"failed: {e}")

        # 5. Prepare application packages (strong fits + tailored near-misses).
        prepared = 0
        for m in strong + [m for m in near if m.get("tailoring")]:
            exists = db.query(Application).filter(
                Application.user_id == user.user_id, Application.job_id == m["job_id"]
            ).first()
            if exists:
                continue
            db.add(Application(
                application_id=str(uuid.uuid4()),
                user_id=user.user_id,
                resume_id=resume.resume_id,
                job_id=m["job_id"],
                match_id=match_id_by_job.get(m["job_id"]),
                status="prepared",
                tailoring=m.get("tailoring"),
                apply_url=m.get("apply_url"),
            ))
            prepared += 1
        db.commit()
        audit.record("prepare_applications", {}, f"{prepared} application packages prepared")

        # 6. Notify: one digest, then remember what was sent.
        digest_jobs = (strong + [m for m in near if m.get("tailoring")])[:MAX_DIGEST_JOBS]
        emailed = False
        if digest_jobs:
            subject, text_body, html_body = notification_service.render_digest(
                user_name=parsed.full_name, matches=digest_jobs,
            )
            to = pref.notify_email or user.email
            emailed = notification_service.send_email(
                to=to, subject=subject, html_body=html_body, text_body=text_body,
            )
            for m in digest_jobs:
                db.add(NotificationLog(
                    id=str(uuid.uuid4()),
                    user_id=user.user_id,
                    job_id=m["job_id"],
                    channel="email" if emailed else "log",
                ))
            db.commit()
            audit.record("notify_user", {"to": to},
                         f"digest with {len(digest_jobs)} jobs {'emailed' if emailed else 'logged (SMTP off)'}")

        summary = (
            f"Scouted {total_new} new jobs across {len(pref.desired_roles)} role queries; "
            f"{len(strong)} strong fits, {len(near)} near-misses ({tailored_count} tailored); "
            f"{prepared} applications prepared; "
            f"digest {'sent' if emailed else 'not sent' if digest_jobs else 'skipped (nothing new)'}"
        )
        audit.finish("completed", summary)
        return {
            "skipped": False,
            "run_id": audit.run.run_id,
            "new_jobs": total_new,
            "strong_fits": len(strong),
            "near_misses": len(near),
            "tailored": tailored_count,
            "applications_prepared": prepared,
            "digest_emailed": emailed,
            "summary": summary,
        }
    except Exception as e:
        logger.exception("Daily cycle failed for user %s", user.user_id)
        audit.finish("failed", f"{type(e).__name__}: {e}")
        return {"skipped": False, "run_id": audit.run.run_id, "error": str(e)}


def run_daily_cycle_all_users(db: Session) -> list[dict]:
    """Scheduler entry point: every user with the digest enabled gets a cycle."""
    users = (
        db.query(User)
        .join(UserPreference, UserPreference.user_id == User.user_id)
        .filter(UserPreference.daily_digest_enabled.is_(True))
        .all()
    )
    results = []
    for user in users:
        results.append(run_daily_cycle_for_user(db, user))
    return results
