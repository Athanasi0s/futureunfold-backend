"""
Certification service — computes milestone rankings for each user
across 10 engagement categories.

Each milestone shows the user's count, rank among all users, and
percentile position. Used for generating digital certificates.
"""

from datetime import datetime

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_agenda import UserAgenda
from app.models.session import Session as SessionModel
from app.models.scan_log import ScanLog
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.message import Message
from app.models.meeting import Meeting
from app.models.point_transaction import PointTransaction
from app.models.poll_answer import PollAnswer
from app.core.enums import MeetingStatus
from app.services.config_reader import get_config_value


# Milestone category definitions: (key, label, icon)
MILESTONE_CATEGORIES = [
    ("session_explorer", "Session Explorer", "calendar-outline"),
    ("social_butterfly", "Social Butterfly", "qr-code-outline"),
    ("network_builder", "Network Builder", "people-outline"),
    ("community_leader", "Community Leader", "chatbubbles-outline"),
    ("meeting_master", "Meeting Master", "handshake-outline"),
    ("early_bird", "Early Bird", "sunny-outline"),
    ("poll_champion", "Poll Champion", "bar-chart-outline"),
    ("festival_veteran", "Festival Veteran", "trophy-outline"),
    ("curious_mind", "Curious Mind", "bulb-outline"),
    ("team_player", "Team Player", "megaphone-outline"),
]


def _get_festival_start(db: Session) -> str:
    """Get festival start date from config, default 2026-05-20."""
    schedule_config = get_config_value(db, "schedule_config", {})
    if isinstance(schedule_config, dict):
        return schedule_config.get("festival_start", "2026-05-20")
    return "2026-05-20"


def _ranked_counts(all_counts: dict[int, int], user_id: int) -> tuple[int, int, int, float]:
    """
    Given {user_id: count} mapping, compute rank and percentile for user_id.
    Returns (count, rank, total_users, percentile).
    """
    if not all_counts or user_id not in all_counts:
        return 0, 0, 0, 0.0

    user_count = all_counts[user_id]
    if user_count == 0:
        return 0, 0, 0, 0.0

    # Sort descending by count
    sorted_users = sorted(all_counts.items(), key=lambda x: (-x[1], x[0]))
    total_users = len(sorted_users)

    # Find user's rank (1-based)
    user_rank = 0
    for idx, (uid, cnt) in enumerate(sorted_users):
        if uid == user_id:
            user_rank = idx + 1
            break

    if total_users > 0:
        percentile = round(((total_users - user_rank) / total_users) * 100, 1)
    else:
        percentile = 0.0

    return user_count, user_rank, total_users, percentile


def compute_milestones(db: Session, user_id: int, custom_titles: dict | None = None) -> list[dict]:
    """
    Compute milestone rankings for the given user across 10 categories.

    For each category, runs a single aggregate query over ALL users,
    finds the target user's rank and percentile.

    Args:
        db: Database session
        user_id: Target user ID
        custom_titles: Optional dict mapping category keys (e.g. "session_explorer")
                       to custom display labels. When provided, overrides default labels.

    Returns list of non-zero milestones sorted by percentile DESC.
    """
    if custom_titles is None:
        custom_titles = {}
    results: list[dict] = []

    # 1. Session Explorer: COUNT of UserAgenda rows per user
    agenda_counts = dict(
        db.query(UserAgenda.user_id, func.count(UserAgenda.id))
        .group_by(UserAgenda.user_id)
        .all()
    )
    _add_milestone(results, "session_explorer", custom_titles.get("session_explorer", "Session Explorer"), "calendar-outline",
                   agenda_counts, user_id)

    # 2. Social Butterfly: COUNT of ScanLog where scanner_id = user
    scan_counts = dict(
        db.query(ScanLog.scanner_id, func.count(ScanLog.id))
        .group_by(ScanLog.scanner_id)
        .all()
    )
    _add_milestone(results, "social_butterfly", custom_titles.get("social_butterfly", "Social Butterfly"), "qr-code-outline",
                   scan_counts, user_id)

    # 3. Network Builder: COUNT of GroupMember rows per user
    group_counts = dict(
        db.query(GroupMember.user_id, func.count(GroupMember.id))
        .group_by(GroupMember.user_id)
        .all()
    )
    _add_milestone(results, "network_builder", custom_titles.get("network_builder", "Network Builder"), "people-outline",
                   group_counts, user_id)

    # 4. Community Leader: GroupMessage(text) + Message(DM) combined count
    gm_counts = dict(
        db.query(GroupMessage.sender_id, func.count(GroupMessage.id))
        .filter(GroupMessage.message_type == "text")
        .group_by(GroupMessage.sender_id)
        .all()
    )
    dm_counts = dict(
        db.query(Message.sender_id, func.count(Message.id))
        .group_by(Message.sender_id)
        .all()
    )
    # Merge counts
    all_user_ids = set(gm_counts.keys()) | set(dm_counts.keys())
    community_counts = {
        uid: gm_counts.get(uid, 0) + dm_counts.get(uid, 0)
        for uid in all_user_ids
    }
    _add_milestone(results, "community_leader", custom_titles.get("community_leader", "Community Leader"), "chatbubbles-outline",
                   community_counts, user_id)

    # 5. Meeting Master: COUNT of Meeting where user is participant AND confirmed
    # Need to count per user — each meeting counts for both participants
    meeting_req = dict(
        db.query(Meeting.requester_id, func.count(Meeting.id))
        .filter(Meeting.status == MeetingStatus.confirmed)
        .group_by(Meeting.requester_id)
        .all()
    )
    meeting_rec = dict(
        db.query(Meeting.recipient_id, func.count(Meeting.id))
        .filter(Meeting.status == MeetingStatus.confirmed)
        .group_by(Meeting.recipient_id)
        .all()
    )
    all_meeting_ids = set(meeting_req.keys()) | set(meeting_rec.keys())
    meeting_counts = {
        uid: meeting_req.get(uid, 0) + meeting_rec.get(uid, 0)
        for uid in all_meeting_ids
    }
    _add_milestone(results, "meeting_master", custom_titles.get("meeting_master", "Meeting Master"), "handshake-outline",
                   meeting_counts, user_id)

    # 6. Early Bird: COUNT of PointTransaction on festival day 1
    festival_start_str = _get_festival_start(db)
    try:
        festival_start = datetime.strptime(festival_start_str, "%Y-%m-%d")
        day1_start = festival_start
        day1_end = festival_start.replace(hour=23, minute=59, second=59)
    except (ValueError, TypeError):
        day1_start = datetime(2026, 5, 20)
        day1_end = datetime(2026, 5, 20, 23, 59, 59)

    early_counts = dict(
        db.query(PointTransaction.user_id, func.count(PointTransaction.id))
        .filter(
            PointTransaction.created_at >= day1_start,
            PointTransaction.created_at <= day1_end,
        )
        .group_by(PointTransaction.user_id)
        .all()
    )
    _add_milestone(results, "early_bird", custom_titles.get("early_bird", "Early Bird"), "sunny-outline",
                   early_counts, user_id)

    # 7. Poll Champion: COUNT of PollAnswer rows per user
    poll_counts = dict(
        db.query(PollAnswer.user_id, func.count(PollAnswer.id))
        .group_by(PollAnswer.user_id)
        .all()
    )
    _add_milestone(results, "poll_champion", custom_titles.get("poll_champion", "Poll Champion"), "bar-chart-outline",
                   poll_counts, user_id)

    # 8. Festival Veteran: User.points raw value
    point_counts = dict(
        db.query(User.id, User.points)
        .filter(User.points > 0)
        .all()
    )
    _add_milestone(results, "festival_veteran", custom_titles.get("festival_veteran", "Festival Veteran"), "trophy-outline",
                   point_counts, user_id)

    # 9. Curious Mind: COUNT DISTINCT session.type from UserAgenda joined with Session
    curious_counts = dict(
        db.query(
            UserAgenda.user_id,
            func.count(func.distinct(SessionModel.type)),
        )
        .join(SessionModel, SessionModel.id == UserAgenda.session_id)
        .group_by(UserAgenda.user_id)
        .all()
    )
    _add_milestone(results, "curious_mind", custom_titles.get("curious_mind", "Curious Mind"), "bulb-outline",
                   curious_counts, user_id)

    # 10. Team Player: COUNT of groups where user sent 3+ GroupMessages
    # Subquery: groups per user where message count >= 3
    from sqlalchemy import literal_column
    active_groups_sub = (
        db.query(
            GroupMessage.sender_id.label("user_id"),
            func.count(func.distinct(GroupMessage.group_id)).label("active_count"),
        )
        .filter(GroupMessage.message_type == "text")
        .group_by(GroupMessage.sender_id, GroupMessage.group_id)
        .having(func.count(GroupMessage.id) >= 3)
        .subquery()
    )
    team_counts_raw = (
        db.query(
            active_groups_sub.c.user_id,
            func.count(active_groups_sub.c.active_count),
        )
        .group_by(active_groups_sub.c.user_id)
        .all()
    )
    team_counts = dict(team_counts_raw)
    _add_milestone(results, "team_player", custom_titles.get("team_player", "Team Player"), "megaphone-outline",
                   team_counts, user_id)

    # Sort by percentile descending
    results.sort(key=lambda m: -m["percentile"])

    return results


def _add_milestone(
    results: list[dict],
    category: str,
    label: str,
    icon: str,
    all_counts: dict[int, int],
    user_id: int,
) -> None:
    """Compute rank for user and append to results if count > 0."""
    count, rank, total_users, percentile = _ranked_counts(all_counts, user_id)
    if count == 0:
        return

    top_pct = max(1, round(100 - percentile))
    rank_label = f"#{rank} of {total_users} (Top {top_pct}%)"

    results.append({
        "category": label,
        "icon": icon,
        "count": count,
        "rank": rank,
        "total_users": total_users,
        "percentile": percentile,
        "rank_label": rank_label,
    })
