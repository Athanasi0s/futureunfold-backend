"""
Leaderboard service — snapshot job and live query logic for the
enhanced multi-category leaderboard.

Categories:
  - points:   User.points (cumulative)
  - sessions: UserAgenda + PollAnswer + SessionQuestion counts
  - groups:   GroupMember + GroupMessage (by sender_id) counts
  - scans:    ScanLog rows (scanner_id OR scanned_id via UNION ALL)
"""

import logging
from datetime import date, timedelta

from sqlalchemy import func, literal_column, union_all, select, case, Integer
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.user import User
from app.models.user_agenda import UserAgenda
from app.models.poll_answer import PollAnswer
from app.models.session_question import SessionQuestion
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.scan_log import ScanLog

logger = logging.getLogger(__name__)

CATEGORIES = ("points", "sessions", "groups", "scans")


# ---------------------------------------------------------------------------
# Helper: build a live count query for a given category
# ---------------------------------------------------------------------------

def _live_points_query(db: Session, date_filter: date | None = None):
    """Points are cumulative on User.points — no date filter applies."""
    return (
        db.query(
            User.id.label("user_id"),
            User.full_name,
            User.avatar_url,
            User.role,
            User.points.label("count"),
        )
        .filter(User.points > 0)
    )


def _live_sessions_query(db: Session, date_filter: date | None = None):
    """Sessions engagement = UserAgenda + PollAnswer + SessionQuestion counts."""
    next_day = date_filter + timedelta(days=1) if date_filter else None

    # Subquery: user_agenda counts
    agenda_q = db.query(
        UserAgenda.user_id.label("user_id"),
        func.count().label("cnt"),
    )
    if date_filter:
        agenda_q = agenda_q.filter(
            UserAgenda.created_at >= date_filter,
            UserAgenda.created_at < next_day,
        )
    agenda_sub = agenda_q.group_by(UserAgenda.user_id).subquery("agenda")

    # Subquery: poll_answers counts
    votes_q = db.query(
        PollAnswer.user_id.label("user_id"),
        func.count().label("cnt"),
    )
    if date_filter:
        votes_q = votes_q.filter(
            PollAnswer.created_at >= date_filter,
            PollAnswer.created_at < next_day,
        )
    votes_sub = votes_q.group_by(PollAnswer.user_id).subquery("votes")

    # Subquery: session_questions counts
    questions_q = db.query(
        SessionQuestion.user_id.label("user_id"),
        func.count().label("cnt"),
    )
    if date_filter:
        questions_q = questions_q.filter(
            SessionQuestion.created_at >= date_filter,
            SessionQuestion.created_at < next_day,
        )
    questions_sub = questions_q.group_by(SessionQuestion.user_id).subquery("questions")

    total_count = (
        func.coalesce(agenda_sub.c.cnt, 0)
        + func.coalesce(votes_sub.c.cnt, 0)
        + func.coalesce(questions_sub.c.cnt, 0)
    )

    return (
        db.query(
            User.id.label("user_id"),
            User.full_name,
            User.avatar_url,
            User.role,
            total_count.label("count"),
        )
        .outerjoin(agenda_sub, agenda_sub.c.user_id == User.id)
        .outerjoin(votes_sub, votes_sub.c.user_id == User.id)
        .outerjoin(questions_sub, questions_sub.c.user_id == User.id)
        .filter(total_count > 0)
    )


def _live_groups_query(db: Session, date_filter: date | None = None):
    """Groups engagement = GroupMember + GroupMessage (by sender_id) counts."""
    next_day = date_filter + timedelta(days=1) if date_filter else None

    members_q = db.query(
        GroupMember.user_id.label("user_id"),
        func.count().label("cnt"),
    )
    if date_filter:
        members_q = members_q.filter(
            GroupMember.joined_at >= date_filter,
            GroupMember.joined_at < next_day,
        )
    members_sub = members_q.group_by(GroupMember.user_id).subquery("members")

    messages_q = db.query(
        GroupMessage.sender_id.label("user_id"),
        func.count().label("cnt"),
    )
    if date_filter:
        messages_q = messages_q.filter(
            GroupMessage.created_at >= date_filter,
            GroupMessage.created_at < next_day,
        )
    messages_sub = messages_q.group_by(GroupMessage.sender_id).subquery("messages")

    total_count = (
        func.coalesce(members_sub.c.cnt, 0)
        + func.coalesce(messages_sub.c.cnt, 0)
    )

    return (
        db.query(
            User.id.label("user_id"),
            User.full_name,
            User.avatar_url,
            User.role,
            total_count.label("count"),
        )
        .outerjoin(members_sub, members_sub.c.user_id == User.id)
        .outerjoin(messages_sub, messages_sub.c.user_id == User.id)
        .filter(total_count > 0)
    )


def _live_scans_query(db: Session, date_filter: date | None = None):
    """Scans = UNION ALL of scanner_id and scanned_id from scan_logs."""
    next_day = date_filter + timedelta(days=1) if date_filter else None

    scanner_q = db.query(ScanLog.scanner_id.label("user_id"))
    scanned_q = db.query(ScanLog.scanned_id.label("user_id"))

    if date_filter:
        scanner_q = scanner_q.filter(
            ScanLog.created_at >= date_filter,
            ScanLog.created_at < next_day,
        )
        scanned_q = scanned_q.filter(
            ScanLog.created_at >= date_filter,
            ScanLog.created_at < next_day,
        )

    union_sub = union_all(scanner_q, scanned_q).subquery("scans_union")

    scan_counts = (
        db.query(
            union_sub.c.user_id.label("user_id"),
            func.count().label("cnt"),
        )
        .group_by(union_sub.c.user_id)
        .subquery("scan_counts")
    )

    return (
        db.query(
            User.id.label("user_id"),
            User.full_name,
            User.avatar_url,
            User.role,
            func.coalesce(scan_counts.c.cnt, 0).label("count"),
        )
        .join(scan_counts, scan_counts.c.user_id == User.id)
        .filter(scan_counts.c.cnt > 0)
    )


_CATEGORY_QUERY_MAP = {
    "points": _live_points_query,
    "sessions": _live_sessions_query,
    "groups": _live_groups_query,
    "scans": _live_scans_query,
}


# ---------------------------------------------------------------------------
# Public API: get_enhanced_leaderboard
# ---------------------------------------------------------------------------

def get_enhanced_leaderboard(
    db: Session,
    category: str,
    period: str,
    target_date: date | None,
    limit: int,
    current_user_id: int,
):
    """
    Return (entries, my_entry) for the enhanced leaderboard.

    - period="all_time": live aggregation, no date filter
    - period="daily" + target_date == today: live with date filter
    - period="daily" + target_date < today: read from snapshots
    """
    today = date.today()

    # --- Read from snapshots for past dates ---
    if period == "daily" and target_date and target_date < today:
        return _from_snapshots(db, category, target_date, limit, current_user_id)

    # --- Live query ---
    date_filter = target_date if (period == "daily" and target_date) else None
    # Points category ignores date_filter (cumulative)
    query_fn = _CATEGORY_QUERY_MAP[category]
    base_q = query_fn(db, date_filter)

    # Order by count DESC, full_name ASC for tie-breaking
    all_rows = (
        base_q
        .order_by(literal_column("count").desc(), User.full_name.asc())
        .all()
    )

    # Assign ranks (1-based, no gaps — ties get different ranks, broken alphabetically)
    ranked = []
    for idx, row in enumerate(all_rows):
        ranked.append({
            "user_id": row.user_id,
            "full_name": row.full_name,
            "avatar_url": row.avatar_url,
            "role": row.role.value if hasattr(row.role, "value") else (row.role or "attendee"),
            "count": row.count,
            "rank": idx + 1,
        })

    # Top N entries
    entries = ranked[:limit]

    # Find current user's entry
    my_entry = None
    for item in ranked:
        if item["user_id"] == current_user_id:
            my_entry = item
            break

    return entries, my_entry


def _from_snapshots(db: Session, category: str, target_date: date, limit: int, current_user_id: int):
    """Read precomputed snapshot data for a past date, joining with users for profile info."""
    rows = (
        db.query(
            LeaderboardSnapshot.user_id,
            User.full_name,
            User.avatar_url,
            User.role,
            LeaderboardSnapshot.count,
            LeaderboardSnapshot.rank,
        )
        .join(User, User.id == LeaderboardSnapshot.user_id)
        .filter(
            LeaderboardSnapshot.snapshot_date == target_date,
            LeaderboardSnapshot.category == category,
        )
        .order_by(LeaderboardSnapshot.rank)
        .all()
    )

    all_entries = []
    for row in rows:
        all_entries.append({
            "user_id": row.user_id,
            "full_name": row.full_name,
            "avatar_url": row.avatar_url,
            "role": row.role.value if hasattr(row.role, "value") else (row.role or "attendee"),
            "count": row.count,
            "rank": row.rank,
        })

    entries = all_entries[:limit]

    my_entry = None
    for item in all_entries:
        if item["user_id"] == current_user_id:
            my_entry = item
            break

    return entries, my_entry


# ---------------------------------------------------------------------------
# Public API: get_my_stats
# ---------------------------------------------------------------------------

def get_my_stats(db: Session, user_id: int):
    """Compute the user's all-time rank for each of the 4 categories."""
    stats = {}

    for category in CATEGORIES:
        query_fn = _CATEGORY_QUERY_MAP[category]
        base_q = query_fn(db, date_filter=None)

        all_rows = (
            base_q
            .order_by(literal_column("count").desc(), User.full_name.asc())
            .all()
        )

        rank = None
        for idx, row in enumerate(all_rows):
            if row.user_id == user_id:
                rank = idx + 1
                break

        stats[f"{category}_rank"] = rank

    return stats


# ---------------------------------------------------------------------------
# Midnight cron job: run_leaderboard_snapshot
# ---------------------------------------------------------------------------

def run_leaderboard_snapshot():
    """
    Midnight cron job: create snapshot rows for yesterday's leaderboard
    across all 4 categories. Idempotent — skips if snapshots already exist.
    """
    db = SessionLocal()
    try:
        yesterday = date.today() - timedelta(days=1)

        # Idempotency check: skip if any snapshots exist for yesterday
        existing = (
            db.query(LeaderboardSnapshot.id)
            .filter(LeaderboardSnapshot.snapshot_date == yesterday)
            .first()
        )
        if existing:
            logger.info("Snapshots already exist for %s, skipping.", yesterday)
            return

        for category in CATEGORIES:
            _snapshot_category(db, yesterday, category)

        db.commit()
        logger.info("Leaderboard snapshots created for %s", yesterday)
    except Exception:
        db.rollback()
        logger.exception("Failed to create leaderboard snapshots")
        raise
    finally:
        db.close()


def _snapshot_category(db: Session, snapshot_date: date, category: str):
    """Compute and insert snapshot rows for one category on a given date."""
    # For daily snapshots, use date filter (except points which is cumulative)
    date_filter = snapshot_date if category != "points" else None

    query_fn = _CATEGORY_QUERY_MAP[category]
    base_q = query_fn(db, date_filter)

    all_rows = (
        base_q
        .order_by(literal_column("count").desc(), User.full_name.asc())
        .all()
    )

    snapshots = []
    for idx, row in enumerate(all_rows):
        snapshots.append(
            LeaderboardSnapshot(
                snapshot_date=snapshot_date,
                category=category,
                user_id=row.user_id,
                count=row.count,
                rank=idx + 1,
            )
        )

    if snapshots:
        db.add_all(snapshots)
        logger.info(
            "Category '%s' for %s: %d entries", category, snapshot_date, len(snapshots)
        )
