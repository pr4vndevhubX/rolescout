"""
Background scheduling — APScheduler.

Two independent, opt-in jobs (no env var -> no scheduler -> no surprise API usage):

1. Job sync: set JOB_SYNC_QUERIES (semicolon-separated) and every
   JOB_SYNC_INTERVAL_HOURS each query is ingested from all sources and
   embedded — the job pool stays fresh without anyone calling /jobs/ingest.

2. The assistant's daily cycle: set ASSISTANT_ENABLED=true and every day at
   ASSISTANT_DAILY_HOUR each digest-enabled user gets scouted/matched/
   tailored/notified (see app/agent/daily_cycle.py).
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import (
    ASSISTANT_DAILY_HOUR,
    ASSISTANT_ENABLED,
    JOB_SYNC_QUERIES,
    JOB_SYNC_INTERVAL_HOURS,
    JOB_SYNC_COUNTRY,
)
from app.core.database import SessionLocal
from app.services.job_ingestion import ingest_from_sources, embed_pending_jobs

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_assistant_daily() -> None:
    # Imported here so the agent stack only loads when the feature is on.
    from app.agent.daily_cycle import run_daily_cycle_all_users

    db = SessionLocal()
    try:
        results = run_daily_cycle_all_users(db)
        ran = [r for r in results if not r.get("skipped")]
        logger.info("Assistant daily cycle: %d users processed, %d skipped",
                    len(ran), len(results) - len(ran))
    except Exception:
        # A failed cycle must never kill the scheduler; next run may succeed.
        logger.exception("Assistant daily cycle failed")
    finally:
        db.close()


def _sync_all_queries() -> None:
    db = SessionLocal()
    try:
        for query in JOB_SYNC_QUERIES:
            result = ingest_from_sources(db, query, country=JOB_SYNC_COUNTRY)
            logger.info(
                "Job sync '%s': %d ingested, %d deduplicated",
                query, result["total_ingested"], result["total_deduplicated"],
            )
        embedded = embed_pending_jobs(db)
        logger.info("Job sync: embedded %d new jobs", embedded)
    except Exception:
        # A failed cycle must never kill the scheduler; next run may succeed.
        logger.exception("Job sync cycle failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not JOB_SYNC_QUERIES and not ASSISTANT_ENABLED:
        logger.info("Scheduler disabled (JOB_SYNC_QUERIES and ASSISTANT_ENABLED not set)")
        return
    if _scheduler is not None:
        return  # already running (uvicorn --reload re-imports modules)

    _scheduler = BackgroundScheduler(daemon=True)

    if JOB_SYNC_QUERIES:
        _scheduler.add_job(
            _sync_all_queries,
            trigger="interval",
            hours=JOB_SYNC_INTERVAL_HOURS,
            id="job_sync",
            max_instances=1,        # never overlap two sync cycles
            coalesce=True,          # missed runs collapse into one
            next_run_time=datetime.now() + timedelta(seconds=15),  # first sync right after boot
        )
        logger.info(
            "Job sync scheduled: %d queries every %dh (country=%s)",
            len(JOB_SYNC_QUERIES), JOB_SYNC_INTERVAL_HOURS, JOB_SYNC_COUNTRY,
        )

    if ASSISTANT_ENABLED:
        _scheduler.add_job(
            _run_assistant_daily,
            trigger="cron",
            hour=ASSISTANT_DAILY_HOUR,
            id="assistant_daily",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Assistant daily cycle scheduled at %02d:00", ASSISTANT_DAILY_HOUR)

    _scheduler.start()
