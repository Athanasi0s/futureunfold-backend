"""
Journey Timeline service — builds a chronological timeline of all user
activities at the festival, grouped by day.

Activity types: session favorites, group joins, QR scans, group messages,
DM messages, confirmed meetings, poll votes.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.models.user_agenda import UserAgenda
from app.models.session import Session as SessionModel
from app.models.group_member import GroupMember
from app.models.group import Group
from app.models.scan_log import ScanLog
from app.models.user import User
from app.models.group_message import GroupMessage
from app.models.message import Message
from app.models.meeting import Meeting
from app.models.poll_answer import PollAnswer
from app.models.poll import Poll
from app.core.enums import MeetingStatus
from app.services.config_reader import get_config_value


def get_journey_timeline(db: Session, user_id: int) -> dict:
    """
    Query 7 activity types, normalize each to a timeline event,
    merge, sort chronologically, and group by festival day.

    Returns {"days": [...], "total_activities": int}.
    """
    events: list[dict] = []

    # 1. Sessions favorited
    agenda_rows = (
        db.query(UserAgenda)
        .options(joinedload(UserAgenda.session))
        .filter(UserAgenda.user_id == user_id)
        .all()
    )
    for row in agenda_rows:
        sess = row.session
        if sess:
            events.append({
                "type": "session",
                "title": sess.title,
                "subtitle": sess.type,
                "icon": "calendar-outline",
                "timestamp": row.created_at,
            })

    # 2. Groups joined
    member_rows = (
        db.query(GroupMember, Group)
        .join(Group, Group.id == GroupMember.group_id)
        .filter(GroupMember.user_id == user_id)
        .all()
    )
    for gm, group in member_rows:
        events.append({
            "type": "group",
            "title": group.title,
            "subtitle": "Joined group",
            "icon": "people-outline",
            "timestamp": gm.joined_at,
        })

    # 3. QR scans (user is the scanner)
    scan_rows = (
        db.query(ScanLog)
        .options(joinedload(ScanLog.scanned))
        .filter(ScanLog.scanner_id == user_id)
        .all()
    )
    for scan in scan_rows:
        scanned_user = scan.scanned
        events.append({
            "type": "scan",
            "title": scanned_user.full_name if scanned_user else "Unknown",
            "subtitle": "QR scan",
            "icon": "qr-code-outline",
            "timestamp": scan.created_at,
        })

    # 4. Group messages sent (text only)
    gm_rows = (
        db.query(GroupMessage, Group)
        .join(Group, Group.id == GroupMessage.group_id)
        .filter(
            GroupMessage.sender_id == user_id,
            GroupMessage.message_type == "text",
        )
        .all()
    )
    for msg, group in gm_rows:
        events.append({
            "type": "message",
            "title": group.title,
            "subtitle": "Group message",
            "icon": "chatbubble-outline",
            "timestamp": msg.created_at,
        })

    # 5. DM messages sent
    dm_rows = (
        db.query(Message)
        .filter(Message.sender_id == user_id)
        .all()
    )
    for msg in dm_rows:
        events.append({
            "type": "message",
            "title": "Direct message",
            "subtitle": None,
            "icon": "mail-outline",
            "timestamp": msg.created_at,
        })

    # 6. Meetings (confirmed, user is requester or recipient)
    meeting_rows = (
        db.query(Meeting)
        .options(joinedload(Meeting.requester), joinedload(Meeting.recipient))
        .filter(
            Meeting.status == MeetingStatus.confirmed,
            (Meeting.requester_id == user_id) | (Meeting.recipient_id == user_id),
        )
        .all()
    )
    for m in meeting_rows:
        other = m.recipient if m.requester_id == user_id else m.requester
        events.append({
            "type": "meeting",
            "title": other.full_name if other else "Unknown",
            "subtitle": "Meeting",
            "icon": "handshake-outline",
            "timestamp": m.created_at,
        })

    # 7. Poll votes
    poll_rows = (
        db.query(PollAnswer)
        .options(joinedload(PollAnswer.poll))
        .filter(PollAnswer.user_id == user_id)
        .all()
    )
    for pa in poll_rows:
        poll = pa.poll
        question = poll.question if poll else "Poll"
        if len(question) > 50:
            question = question[:50]
        events.append({
            "type": "poll",
            "title": question,
            "subtitle": "Poll vote",
            "icon": "bar-chart-outline",
            "timestamp": pa.created_at,
        })

    # Sort by timestamp ascending
    events.sort(key=lambda e: e["timestamp"])

    # Get festival start date for day labelling
    schedule_config = get_config_value(db, "schedule_config", {})
    festival_start_str = schedule_config.get("festival_start", "2026-05-20") if isinstance(schedule_config, dict) else "2026-05-20"
    try:
        festival_start = datetime.strptime(festival_start_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        festival_start = datetime(2026, 5, 20).date()

    # Group by day
    day_groups: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        ts = event["timestamp"]
        date_key = ts.strftime("%Y-%m-%d")
        day_groups[date_key].append({
            "type": event["type"],
            "title": event["title"],
            "subtitle": event["subtitle"],
            "icon": event["icon"],
            "timestamp": ts.isoformat(),
        })

    # Build sorted day list
    days = []
    for date_key in sorted(day_groups.keys()):
        event_date = datetime.strptime(date_key, "%Y-%m-%d").date()
        day_number = (event_date - festival_start).days + 1
        day_label = f"Day {day_number} - {event_date.strftime('%b %d')}"
        days.append({
            "date": date_key,
            "day_label": day_label,
            "events": day_groups[date_key],
        })

    return {
        "days": days,
        "total_activities": len(events),
    }
