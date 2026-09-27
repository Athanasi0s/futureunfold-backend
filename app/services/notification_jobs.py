"""
Scheduled notification job functions.

Each function is called by APScheduler on a fixed interval.
They query the database for relevant events and send push
notifications via the batch helper in app.services.push.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_suggestion_sent import GroupSuggestionSent
from app.models.meeting import Meeting
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.models.session import Session as ProgramSession
from app.models.user import User
from app.models.user_agenda import UserAgenda
from app.core.enums import MeetingStatus
from app.services.config_reader import get_config_value
from app.services.friends import get_friend_ids
from app.services.push import send_push_batch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DEFAULT_DAILY_CAP = 20  # fallback if AppConfig key not set


def _is_within_festival_window(db: Session) -> bool:
    """Return True if smart notifications are enabled and today is within
    the configured festival date range (inclusive)."""
    enabled = get_config_value(db, "smart_notif_enabled", True)
    if not enabled:
        return False

    start_raw = get_config_value(db, "festival_date_start")
    end_raw = get_config_value(db, "festival_date_end")
    if not start_raw or not end_raw:
        return False

    try:
        start_date = date.fromisoformat(str(start_raw))
        end_date = date.fromisoformat(str(end_raw))
    except (ValueError, TypeError):
        logger.warning("Could not parse festival dates: %s / %s", start_raw, end_raw)
        return False

    today = datetime.now(timezone.utc).date()
    return start_date <= today <= end_date


def _get_daily_notification_count(db: Session, user_id: int) -> int:
    """Count notifications sent to *user_id* since midnight UTC today."""
    midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= midnight,
        )
        .scalar()
    )
    return count or 0


def _is_preference_enabled(db: Session, user_id: int, category: str) -> bool:
    """Check if the user has the given notification category enabled.
    No row means enabled by default."""
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
        .first()
    )
    if pref is None:
        return True
    return pref.enabled


def _already_notified(
    db: Session, user_id: int, notif_type: str, ref_id: int
) -> bool:
    """Return True if a notification with the same type+ref_id already
    exists for the user (dedup guard)."""
    return (
        db.query(
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.type == notif_type,
                Notification.ref_id == ref_id,
            )
            .exists()
        ).scalar()
    )


def _can_send(
    db: Session, user_id: int, category: str, daily_cap: int | None = None
) -> bool:
    """Return True if user's preference is enabled AND the daily cap has
    not been reached.  Reads cap from AppConfig if not provided."""
    if not _is_preference_enabled(db, user_id, category):
        return False
    if daily_cap is None:
        daily_cap = int(get_config_value(db, "smart_notif_daily_cap", DEFAULT_DAILY_CAP))
    if _get_daily_notification_count(db, user_id) >= daily_cap:
        return False
    return True


def _get_friends_cached(
    db: Session, user_id: int, cache: dict[int, set[int]]
) -> set[int]:
    """Return friend IDs for *user_id*, using *cache* to avoid repeated
    queries within a single job run."""
    if user_id not in cache:
        cache[user_id] = get_friend_ids(db, user_id)
    return cache[user_id]


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


def run_session_reminders() -> None:
    """Notify users about sessions starting in ~30 minutes.
    Runs every 10 min; queries sessions starting in the 20-30 min window."""
    db = SessionLocal()
    try:
        if not _is_within_festival_window(db):
            return

        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=20)
        window_end = now + timedelta(minutes=30)

        sessions = (
            db.query(ProgramSession)
            .filter(
                ProgramSession.start_time >= window_start,
                ProgramSession.start_time <= window_end,
            )
            .all()
        )
        if not sessions:
            return

        friend_cache: dict[int, set[int]] = {}
        batch: list[dict] = []

        for sess in sessions:
            # Get all users who favorited this session
            favoriters = (
                db.query(UserAgenda.user_id)
                .filter(UserAgenda.session_id == sess.id)
                .all()
            )
            favoriter_ids = {row[0] for row in favoriters}

            for uid in favoriter_ids:
                if _already_notified(db, uid, "session_reminder", sess.id):
                    continue
                if not _can_send(db, uid, "session_reminder"):
                    continue

                # Count friends also attending
                friends = _get_friends_cached(db, uid, friend_cache)
                friend_count = len(friends & favoriter_ids)

                if friend_count > 0:
                    body = f"Starting in 30min \u2014 {friend_count} friends attending"
                else:
                    body = "Starting in 30min"

                batch.append(
                    {
                        "user_id": uid,
                        "title": sess.title,
                        "body": body,
                        "notif_type": "session_reminder",
                        "ref_id": sess.id,
                        "deeplink": f"panathenea://session/{sess.id}",
                    }
                )

        if batch:
            db.commit()  # commit any pending state before push
            send_push_batch(db, batch)
            db.commit()
            logger.info("Session reminders sent: %d", len(batch))

    except Exception:
        logger.exception("Error in run_session_reminders")
    finally:
        db.close()


def run_meeting_reminders() -> None:
    """Notify users about confirmed meetings starting in ~30 minutes.
    Runs every 10 min; queries meetings starting in the 20-30 min window."""
    db = SessionLocal()
    try:
        if not _is_within_festival_window(db):
            return

        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=20)
        window_end = now + timedelta(minutes=30)

        meetings = (
            db.query(Meeting)
            .filter(
                Meeting.status == MeetingStatus.confirmed,
                Meeting.proposed_start >= window_start,
                Meeting.proposed_start <= window_end,
            )
            .all()
        )
        if not meetings:
            return

        batch: list[dict] = []

        for mtg in meetings:
            # Notify requester about recipient
            if not _already_notified(db, mtg.requester_id, "meeting_reminder", mtg.id):
                if _can_send(db, mtg.requester_id, "meeting_reminder"):
                    recipient_name = mtg.recipient.full_name or "Someone"
                    batch.append(
                        {
                            "user_id": mtg.requester_id,
                            "title": f"Meeting with {recipient_name}",
                            "body": "In 30 minutes",
                            "notif_type": "meeting_reminder",
                            "ref_id": mtg.id,
                            "deeplink": f"panathenea://scheduling/{mtg.id}",
                        }
                    )

            # Notify recipient about requester
            if not _already_notified(db, mtg.recipient_id, "meeting_reminder", mtg.id):
                if _can_send(db, mtg.recipient_id, "meeting_reminder"):
                    requester_name = mtg.requester.full_name or "Someone"
                    batch.append(
                        {
                            "user_id": mtg.recipient_id,
                            "title": f"Meeting with {requester_name}",
                            "body": "In 30 minutes",
                            "notif_type": "meeting_reminder",
                            "ref_id": mtg.id,
                            "deeplink": f"panathenea://scheduling/{mtg.id}",
                        }
                    )

        if batch:
            db.commit()
            send_push_batch(db, batch)
            db.commit()
            logger.info("Meeting reminders sent: %d", len(batch))

    except Exception:
        logger.exception("Error in run_meeting_reminders")
    finally:
        db.close()


def run_friend_activity() -> None:
    """Notify users when a friend adds a session to their agenda.
    Runs every 10 min; looks at UserAgenda rows created in the last 10 min."""
    db = SessionLocal()
    try:
        if not _is_within_festival_window(db):
            return

        now = datetime.now(timezone.utc)
        ten_min_ago = now - timedelta(minutes=10)

        # Recently favorited *future* sessions
        recent_favs = (
            db.query(UserAgenda)
            .join(ProgramSession, UserAgenda.session_id == ProgramSession.id)
            .filter(
                UserAgenda.created_at >= ten_min_ago,
                ProgramSession.start_time > now,
            )
            .all()
        )
        if not recent_favs:
            return

        friend_cache: dict[int, set[int]] = {}
        batch: list[dict] = []

        # Pre-fetch user names for the favoriters
        favoriter_ids = {fav.user_id for fav in recent_favs}
        users = (
            db.query(User.id, User.full_name)
            .filter(User.id.in_(favoriter_ids))
            .all()
        )
        name_map = {u.id: u.full_name or "A friend" for u in users}

        # Group recent favs by session to avoid duplicating work
        session_favoriters: dict[int, list[int]] = {}
        session_obj: dict[int, ProgramSession] = {}
        for fav in recent_favs:
            session_favoriters.setdefault(fav.session_id, []).append(fav.user_id)
            if fav.session_id not in session_obj:
                session_obj[fav.session_id] = fav.session

        for sess_id, fav_user_ids in session_favoriters.items():
            sess = session_obj[sess_id]

            # All users who already have this session in their agenda
            existing_favoriter_ids = {
                row[0]
                for row in db.query(UserAgenda.user_id)
                .filter(UserAgenda.session_id == sess_id)
                .all()
            }

            for fav_uid in fav_user_ids:
                friends = _get_friends_cached(db, fav_uid, friend_cache)
                fav_name = name_map.get(fav_uid, "A friend")

                for friend_id in friends:
                    # Skip friends who already favorited this session
                    if friend_id in existing_favoriter_ids:
                        continue

                    if _already_notified(db, friend_id, "friend_activity", sess_id):
                        continue
                    if not _can_send(db, friend_id, "friend_activity"):
                        continue

                    # Suppress if friend has 5+ sessions in the same time slot
                    slot_start = sess.start_time - timedelta(hours=1)
                    slot_end = sess.start_time + timedelta(hours=1)
                    overlapping = (
                        db.query(func.count(UserAgenda.id))
                        .join(
                            ProgramSession,
                            UserAgenda.session_id == ProgramSession.id,
                        )
                        .filter(
                            UserAgenda.user_id == friend_id,
                            ProgramSession.start_time >= slot_start,
                            ProgramSession.start_time <= slot_end,
                        )
                        .scalar()
                    )
                    if (overlapping or 0) >= 5:
                        continue

                    batch.append(
                        {
                            "user_id": friend_id,
                            "title": f"{fav_name} added a session",
                            "body": f"'{sess.title}' \u2014 check it out!",
                            "notif_type": "friend_activity",
                            "ref_id": sess_id,
                            "deeplink": f"panathenea://session/{sess_id}",
                        }
                    )

        if batch:
            db.commit()
            send_push_batch(db, batch)
            db.commit()
            logger.info("Friend activity notifications sent: %d", len(batch))

    except Exception:
        logger.exception("Error in run_friend_activity")
    finally:
        db.close()


def run_popular_sessions() -> None:
    """Notify users when a session is trending among their friends.
    Runs every 30 min."""
    db = SessionLocal()
    try:
        if not _is_within_festival_window(db):
            return

        now = datetime.now(timezone.utc)
        threshold = int(
            get_config_value(db, "smart_notif_popular_threshold", 3) or 3
        )

        # Future sessions
        future_sessions = (
            db.query(ProgramSession)
            .filter(ProgramSession.start_time > now)
            .all()
        )
        if not future_sessions:
            return

        friend_cache: dict[int, set[int]] = {}
        batch: list[dict] = []

        # Collect all users for efficient friend lookups
        all_user_ids = {
            row[0] for row in db.query(User.id).all()
        }

        for sess in future_sessions:
            favoriter_rows = (
                db.query(UserAgenda.user_id)
                .filter(UserAgenda.session_id == sess.id)
                .all()
            )
            favoriter_ids = {row[0] for row in favoriter_rows}
            if not favoriter_ids:
                continue

            # For each user NOT already favoriting, check friend overlap
            for uid in all_user_ids:
                if uid in favoriter_ids:
                    continue

                if _already_notified(db, uid, "popular_session", sess.id):
                    continue

                friends = _get_friends_cached(db, uid, friend_cache)
                friend_count = len(friends & favoriter_ids)

                if friend_count < threshold:
                    continue

                if not _can_send(db, uid, "popular_session"):
                    continue

                batch.append(
                    {
                        "user_id": uid,
                        "title": f"'{sess.title}' is trending",
                        "body": f"{friend_count} friends going",
                        "notif_type": "popular_session",
                        "ref_id": sess.id,
                        "deeplink": f"panathenea://session/{sess.id}",
                    }
                )

        if batch:
            db.commit()
            send_push_batch(db, batch)
            db.commit()
            logger.info("Popular session notifications sent: %d", len(batch))

    except Exception:
        logger.exception("Error in run_popular_sessions")
    finally:
        db.close()


def run_group_suggestions() -> None:
    """Suggest groups to users where 3+ friends are already members.
    Runs every 6 hours. Uses GroupSuggestionSent for dedup."""
    db = SessionLocal()
    try:
        if not _is_within_festival_window(db):
            return

        # Load all groups
        groups = db.query(Group).all()
        if not groups:
            return

        # Build group -> member set mapping
        all_memberships = db.query(GroupMember.group_id, GroupMember.user_id).all()
        group_members: dict[int, set[int]] = {}
        user_groups: dict[int, set[int]] = {}
        for gid, uid in all_memberships:
            group_members.setdefault(gid, set()).add(uid)
            user_groups.setdefault(uid, set()).add(gid)

        # All users
        all_user_ids = {row[0] for row in db.query(User.id).all()}

        # Already-sent suggestions (load all at once for efficiency)
        sent_rows = db.query(
            GroupSuggestionSent.user_id, GroupSuggestionSent.group_id
        ).all()
        sent_set: set[tuple[int, int]] = {(r[0], r[1]) for r in sent_rows}

        friend_cache: dict[int, set[int]] = {}
        group_name_map = {g.id: g.title for g in groups}
        batch: list[dict] = []

        for uid in all_user_ids:
            joined = user_groups.get(uid, set())
            friends = _get_friends_cached(db, uid, friend_cache)
            if not friends:
                continue

            for g in groups:
                if g.id in joined:
                    continue
                if (uid, g.id) in sent_set:
                    continue

                members = group_members.get(g.id, set())
                friend_count = len(friends & members)
                if friend_count < 3:
                    continue

                if not _can_send(db, uid, "group_suggestion"):
                    continue

                # Record that we sent this suggestion
                db.add(GroupSuggestionSent(user_id=uid, group_id=g.id))

                batch.append(
                    {
                        "user_id": uid,
                        "title": f"Join '{g.title}'?",
                        "body": f"{friend_count} of your friends are members",
                        "notif_type": "group_suggestion",
                        "ref_id": g.id,
                        "deeplink": f"panathenea://group/{g.id}",
                    }
                )

        if batch:
            db.commit()
            send_push_batch(db, batch)
            db.commit()
            logger.info("Group suggestion notifications sent: %d", len(batch))

    except Exception:
        logger.exception("Error in run_group_suggestions")
    finally:
        db.close()
