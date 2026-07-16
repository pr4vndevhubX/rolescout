from sqlalchemy import Boolean, Column, String, DateTime, Text, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone

from app.core.database import Base

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output size

VALID_MATCH_STATUSES = {"new", "saved", "dismissed", "applied"}


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)  # salted PBKDF2, never plaintext
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ResumeRecord(Base):
    __tablename__ = "resumes"

    resume_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    # Dedup is per-user (same file from two users = two records), so no unique constraint.
    file_hash = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="uploaded")  # uploaded/extracted/extraction_failed/parsed
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    parsed_data = Column(JSONB, nullable=True)            # structured ParsedResume — queryable JSONB
    confidence_score = Column(Float, nullable=True)
    embedding_vector = Column(Vector(EMBEDDING_DIM), nullable=True)  # pgvector


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True)            # "{source}_{source_id}"
    title = Column(String, nullable=False)
    company = Column(String, nullable=True)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    remote = Column(String, nullable=True)               # "yes"/"no"/None (unknown)
    apply_url = Column(String, nullable=True)
    source = Column(String, nullable=False, default="adzuna")
    dedup_key = Column(String, nullable=True, index=True)  # sha1(title|company) — cross-source dedup
    embedding_vector = Column(Vector(EMBEDDING_DIM), nullable=True)  # searched via HNSW index
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    min_years_required = Column(Float, nullable=True)


class UserPreference(Base):
    """The assistant's standing instructions from the user — one row per user."""

    __tablename__ = "user_preferences"

    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    desired_roles = Column(JSONB, nullable=False, default=list)   # e.g. ["ML Engineer", "GenAI Engineer"]
    country = Column(String, nullable=False, default="in")        # job-source country code
    location_contains = Column(String, nullable=True)             # hard location filter, optional
    min_salary = Column(Float, nullable=True)
    min_match_score = Column(Float, nullable=False, default=0.5)  # blended score -> "strong fit"
    auto_tailor = Column(Boolean, nullable=False, default=True)   # tailor near-miss jobs automatically
    daily_digest_enabled = Column(Boolean, nullable=False, default=True)
    notify_email = Column(String, nullable=True)                  # defaults to account email when unset
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class NotificationLog(Base):
    """One row per (user, job) ever notified — guarantees no duplicate pings."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_notification_user_job"),)

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    channel = Column(String, nullable=False, default="email")
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


VALID_APPLICATION_STATUSES = {"prepared", "approved", "applied", "discarded"}


class Application(Base):
    """A prepared application package: tailored content + cover letter + apply link.

    The agent PREPARES; the human APPROVES; only then is it marked applied.
    Also the dedup ledger — a (user, job) pair is never prepared twice.
    """

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),)

    application_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(String, ForeignKey("resumes.resume_id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    match_id = Column(String, nullable=True)                  # source match, if any
    status = Column(String, nullable=False, default="prepared")
    tailoring = Column(JSONB, nullable=True)                  # tailored summary/bullets/keywords
    cover_letter = Column(Text, nullable=True)
    apply_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    applied_at = Column(DateTime, nullable=True)


class AgentRun(Base):
    """One row per orchestrator run (daily cycle or chat turn) — the audit trail."""

    __tablename__ = "agent_runs"

    run_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    trigger = Column(String, nullable=False)                  # "daily" / "chat" / "manual"
    goal = Column(Text, nullable=True)                        # chat message or cycle goal
    status = Column(String, nullable=False, default="running")  # running/completed/failed
    summary = Column(Text, nullable=True)                     # agent's final report
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)


class AgentAction(Base):
    """Every tool call the agent makes, in order — visible 'why did it do that'."""

    __tablename__ = "agent_actions"

    action_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    tool = Column(String, nullable=False)
    tool_input = Column(JSONB, nullable=True)
    result_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MatchResult(Base):
    __tablename__ = "match_results"

    match_id = Column(String, primary_key=True)
    resume_id = Column(
        String,
        ForeignKey("resumes.resume_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(
        String,
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vector_similarity = Column(Float, nullable=False)
    skill_overlap_ratio = Column(Float, nullable=False)
    blended_score = Column(Float, nullable=False)         # numeric — sorts correctly
    matched_skills = Column(JSONB, nullable=False)
    missing_skills = Column(JSONB, nullable=False)
    explanation = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="new")  # new/saved/dismissed
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ats_score = Column(Float, nullable=True)
    ats_found_keywords = Column(JSONB, nullable=True)
    ats_missing_keywords = Column(JSONB, nullable=True)
    ats_format_score = Column(Float, nullable=True)
