"""
APScheduler configuration for smart notifications.

Creates a BackgroundScheduler with SQLAlchemy job store so that
jobs survive server restarts.  All job functions live in
app.services.notification_jobs.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app.db.session import engine, SessionLocal

logger = logging.getLogger(__name__)


def _run_expire_pending_meetings():
    from app.api.routes.scheduling import expire_pending_meetings
    db = SessionLocal()
    try:
        count = expire_pending_meetings(db)
        if count:
            logger.info("Expired %d pending meetings", count)
    finally:
        db.close()

def create_scheduler() -> BackgroundScheduler:
    """Build a BackgroundScheduler backed by the app's PostgreSQL database."""
    jobstores = {
        "default": SQLAlchemyJobStore(engine=engine),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=3),
    }
    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    }

    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
    )
    return scheduler


def register_jobs(scheduler: BackgroundScheduler) -> None:
    """Register all recurring notification jobs."""
    from app.services.notification_jobs import (
        run_session_reminders,
        run_meeting_reminders,
        run_friend_activity,
        run_group_suggestions,
        run_popular_sessions,
    )
    scheduler.add_job(
        _run_expire_pending_meetings,
        "interval",
        minutes=5,
        id="expire_pending_meetings",
        replace_existing=True,
    )

    scheduler.add_job(
        run_session_reminders,
        "interval",
        minutes=10,
        id="session_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_meeting_reminders,
        "interval",
        minutes=10,
        id="meeting_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_friend_activity,
        "interval",
        minutes=10,
        id="friend_activity",
        replace_existing=True,
    )
    scheduler.add_job(
        run_group_suggestions,
        "interval",
        hours=6,
        id="group_suggestions",
        replace_existing=True,
    )
    scheduler.add_job(
        run_popular_sessions,
        "interval",
        minutes=30,
        id="popular_sessions",
        replace_existing=True,
    )

    # Leaderboard daily snapshot — midnight Athens time
    from app.services.leaderboard import run_leaderboard_snapshot
    from apscheduler.triggers.cron import CronTrigger
    from zoneinfo import ZoneInfo

    scheduler.add_job(
        run_leaderboard_snapshot,
        CronTrigger(hour=0, minute=0, timezone=ZoneInfo("Europe/Athens")),
        id="leaderboard_snapshot",
        replace_existing=True,
    )

    logger.info("Registered %d jobs", len(scheduler.get_jobs()))
