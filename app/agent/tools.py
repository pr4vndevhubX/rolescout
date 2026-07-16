"""
The agent's hands — LangChain tools wrapping the existing services.

Design rules:
- Tools NEVER contain business logic; they call the same services the REST
  API uses, so agent behavior and API behavior can't drift apart.
- Every tool returns a compact human-readable string (the LLM reads it), and
  errors come back as strings too — a failed tool must not kill the run.
- build_tools() closes over (db, user) so the LLM never sees or chooses IDs
  it doesn't own. Ownership is enforced here, not trusted to the model.
"""

import json
import uuid

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agent.context import latest_ready_resume
from app.models.db_models import Application, JobRecord, MatchResult, User, UserPreference
from app.models.parsed_resume import ParsedResume
from app.services import notification_service
from app.services.job_ingestion import embed_pending_jobs, ingest_from_sources
from app.services.match_repository import get_match_by_id, save_match_results
from app.services.matching.ranker import rank_jobs
from app.services.matching.retrieval import get_shortlist
from app.services.resume_text_builder import build_resume_summary_text
from app.services.tailoring_service import generate_cover_letter, tailor_resume_for_job


def _owned_match(db: Session, user: User, match_id: str) -> tuple[MatchResult, JobRecord] | None:
    match = get_match_by_id(db, match_id)
    if not match:
        return None
    resume = latest_ready_resume(db, user.user_id)
    # Ownership: the match must point at one of this user's resumes.
    from app.models.db_models import ResumeRecord
    owner = db.query(ResumeRecord).filter(
        ResumeRecord.resume_id == match.resume_id,
        ResumeRecord.user_id == user.user_id,
    ).first()
    if not owner:
        return None
    job = db.query(JobRecord).filter(JobRecord.job_id == match.job_id).first()
    if not job:
        return None
    return match, job


def build_tools(db: Session, user: User) -> list:
    """All tools bound to this user's session. Returned in a stable order."""

    @tool
    def get_preferences() -> str:
        """Read the user's saved job preferences: desired roles, country, salary floor, thresholds."""
        pref = db.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
        if not pref:
            return "No preferences saved yet. Ask the user what roles they want, or use sensible defaults."
        return json.dumps({
            "desired_roles": pref.desired_roles or [],
            "country": pref.country,
            "location_contains": pref.location_contains,
            "min_salary": pref.min_salary,
            "min_match_score": pref.min_match_score,
            "auto_tailor": pref.auto_tailor,
        })

    @tool
    def search_jobs(query: str, country: str = "in", limit: int = 20) -> str:
        """Search live job boards (Adzuna/Remotive/Arbeitnow) for a role query and store new jobs. Also embeds them for matching."""
        result = ingest_from_sources(db, query, country=country, limit=limit)
        embedded = embed_pending_jobs(db)
        per_source = {name: s["ingested"] for name, s in result["sources"].items()}
        return (
            f"Ingested {result['total_ingested']} new jobs for '{query}' "
            f"({json.dumps(per_source)}), {result['total_deduplicated']} cross-source duplicates skipped, "
            f"{embedded} jobs embedded."
        )

    @tool
    def generate_matches(location_contains: str | None = None, min_salary: float | None = None) -> str:
        """Match the user's resume against all stored jobs. Returns the ranked matches with scores and match_ids."""
        resume = latest_ready_resume(db, user.user_id)
        if not resume:
            return "No matching-ready resume found. The user must upload, parse and embed a resume first."
        parsed = ParsedResume(**resume.parsed_data)
        shortlist = get_shortlist(db, list(resume.embedding_vector), top_n=40)
        ranked = rank_jobs(
            shortlist, parsed,
            resume_summary_text=build_resume_summary_text(parsed),
            resume_raw_text=resume.extracted_text or "",
            location_contains=location_contains,
            min_salary=int(min_salary) if min_salary else None,
        )
        records = save_match_results(db, resume.resume_id, ranked)
        lines = [
            f"- match_id={r.match_id} | {j['title']} at {j.get('company') or '?'} | "
            f"score={r.blended_score:.2f} | missing={', '.join((r.missing_skills or [])[:5]) or 'none'}"
            for r, j in zip(records, ranked)
        ]
        return f"Generated {len(records)} matches:\n" + "\n".join(lines[:15])

    @tool
    def get_matches(status: str | None = None) -> str:
        """List the user's stored job matches (optionally filtered by status: new/saved/dismissed/applied) without recomputing."""
        resume = latest_ready_resume(db, user.user_id)
        if not resume:
            return "No matching-ready resume found."
        query = db.query(MatchResult).filter(MatchResult.resume_id == resume.resume_id)
        if status:
            query = query.filter(MatchResult.status == status)
        matches = query.order_by(MatchResult.blended_score.desc()).limit(15).all()
        if not matches:
            return "No stored matches" + (f" with status '{status}'." if status else ".")
        job_lookup = {
            j.job_id: j for j in db.query(JobRecord).filter(
                JobRecord.job_id.in_([m.job_id for m in matches])).all()
        }
        lines = []
        for m in matches:
            job = job_lookup.get(m.job_id)
            lines.append(
                f"- match_id={m.match_id} | {job.title if job else '?'} at "
                f"{(job.company if job else None) or '?'} | score={m.blended_score:.2f} | status={m.status}"
            )
        return "\n".join(lines)

    @tool
    def tailor_resume(match_id: str) -> str:
        """Adapt the user's resume for one matched job: rewritten summary, bullet rewrites, ATS keywords, honest gaps. Truthful only — never invents experience."""
        found = _owned_match(db, user, match_id)
        if not found:
            return f"Match '{match_id}' not found for this user."
        match, job = found
        resume = latest_ready_resume(db, user.user_id)
        parsed = ParsedResume(**resume.parsed_data)
        suggestions = tailor_resume_for_job(
            resume_summary=build_resume_summary_text(parsed),
            job_title=job.title,
            company=job.company,
            job_description=job.description or "",
            missing_skills=match.missing_skills or [],
            ats_missing_keywords=match.ats_missing_keywords or [],
        )
        return json.dumps(suggestions)

    @tool
    def write_cover_letter(match_id: str) -> str:
        """Write a truthful, job-specific cover letter (250-350 words) for one matched job."""
        found = _owned_match(db, user, match_id)
        if not found:
            return f"Match '{match_id}' not found for this user."
        _, job = found
        resume = latest_ready_resume(db, user.user_id)
        parsed = ParsedResume(**resume.parsed_data)
        return generate_cover_letter(
            resume_summary=build_resume_summary_text(parsed),
            candidate_name=parsed.full_name,
            job_title=job.title,
            company=job.company,
            job_description=job.description or "",
        )

    @tool
    def prepare_application(match_id: str, include_cover_letter: bool = True) -> str:
        """Assemble a ready-to-send application package (tailored resume content + optional cover letter + apply link) for one matched job, queued for the user's approval."""
        found = _owned_match(db, user, match_id)
        if not found:
            return f"Match '{match_id}' not found for this user."
        match, job = found
        existing = db.query(Application).filter(
            Application.user_id == user.user_id, Application.job_id == job.job_id
        ).first()
        if existing:
            return f"Application already prepared for this job (status={existing.status})."

        resume = latest_ready_resume(db, user.user_id)
        parsed = ParsedResume(**resume.parsed_data)
        summary_text = build_resume_summary_text(parsed)
        tailoring = tailor_resume_for_job(
            resume_summary=summary_text,
            job_title=job.title,
            company=job.company,
            job_description=job.description or "",
            missing_skills=match.missing_skills or [],
            ats_missing_keywords=match.ats_missing_keywords or [],
        )
        letter = None
        if include_cover_letter:
            letter = generate_cover_letter(
                resume_summary=summary_text,
                candidate_name=parsed.full_name,
                job_title=job.title,
                company=job.company,
                job_description=job.description or "",
            )
        db.add(Application(
            application_id=str(uuid.uuid4()),
            user_id=user.user_id,
            resume_id=resume.resume_id,
            job_id=job.job_id,
            match_id=match.match_id,
            status="prepared",
            tailoring=tailoring,
            cover_letter=letter,
            apply_url=job.apply_url,
        ))
        db.commit()
        return (
            f"Application package prepared for '{job.title}' at {job.company or '?'} "
            f"(tailored{' + cover letter' if letter else ''}). Awaiting the user's approval; apply link: {job.apply_url}"
        )

    @tool
    def notify_user(subject: str, message: str) -> str:
        """Send the user an email notification (plain message). Use sparingly — e.g. an urgent strong-fit job."""
        pref = db.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
        to = (pref.notify_email if pref and pref.notify_email else user.email)
        sent = notification_service.send_email(
            to=to, subject=subject,
            html_body=f"<div style='font-family:sans-serif'>{message}</div>",
            text_body=message,
        )
        return f"Notification {'sent' if sent else 'logged (SMTP not configured)'} to {to}."

    return [
        get_preferences,
        search_jobs,
        generate_matches,
        get_matches,
        tailor_resume,
        write_cover_letter,
        prepare_application,
        notify_user,
    ]
