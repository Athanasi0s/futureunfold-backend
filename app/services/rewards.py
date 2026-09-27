"""
Centralized Rewards Service — handles point awarding, milestone checks,
and tier computation.

All point-earning actions call award_points() which:
1. Checks for duplicate awards via (user_id, action_type, source_ref) uniqueness
2. Inserts a PointTransaction record
3. Increments User.points
4. Returns result dict with new total and any newly unlocked features

The caller is responsible for calling db.commit() after award_points().
"""

from sqlalchemy.orm import Session as DBSession

from app.models.point_transaction import PointTransaction
from app.models.user import User
from app.services.config_reader import get_config_value


# ──────────────────────────────────────
# Point values per action (from TRD)
# ──────────────────────────────────────
ACTION_POINTS: dict[str, int] = {
    "ATTEND_SESSION": 50,
    "ONBOARDING": 30,
    "RATE_SESSION": 20,
    "JOIN_GROUP": 20,
    "POLL_VOTE": 10,
    "NETWORKING": 10,
    "GROUP_CHAT": 10,
    "MAP_CHECKIN": 10,
    "QR_SCAN": 10,
}


# ──────────────────────────────────────
# Rich action metadata for the frontend
# "How to Earn" card list
# ──────────────────────────────────────
ACTION_CATALOG: list[dict] = [
    {
        "action_type": "ATTEND_SESSION",
        "label": "Attend a session",
        "description": "Scan at entrance",
        "icon": "event_available",
        "points": 50,
        "repeatable": True,
    },
    {
        "action_type": "ONBOARDING",
        "label": "Complete onboarding",
        "description": "Set up your profile & interests",
        "icon": "person_check",
        "points": 30,
        "repeatable": False,
    },
    {
        "action_type": "RATE_SESSION",
        "label": "Rate a session",
        "description": "Submit feedback after attending",
        "icon": "rate_review",
        "points": 20,
        "repeatable": True,
    },
    {
        "action_type": "JOIN_GROUP",
        "label": "Join a topic group",
        "description": "Network with peers",
        "icon": "groups",
        "points": 20,
        "repeatable": True,
    },
    {
        "action_type": "POLL_VOTE",
        "label": "Vote in a poll",
        "description": "Participate in live Q&A or polls",
        "icon": "ballot",
        "points": 10,
        "repeatable": True,
    },
    {
        "action_type": "NETWORKING",
        "label": "Network with someone",
        "description": "Start a conversation via DM",
        "icon": "handshake",
        "points": 10,
        "repeatable": True,
    },
    {
        "action_type": "GROUP_CHAT",
        "label": "Post in group chat",
        "description": "Engage in group discussions",
        "icon": "forum",
        "points": 10,
        "repeatable": True,
    },
    {
        "action_type": "MAP_CHECKIN",
        "label": "Check in at a location",
        "description": "Self check-in via interactive map",
        "icon": "location_on",
        "points": 10,
        "repeatable": True,
    },
    {
        "action_type": "QR_SCAN",
        "label": "Scan an exhibitor QR",
        "description": "Visit exhibition hall",
        "icon": "qr_code_scanner",
        "points": 10,
        "repeatable": True,
    },
]


# ──────────────────────────────────────
# Milestone thresholds (cumulative)
# ──────────────────────────────────────
MILESTONE_THRESHOLDS: list[tuple[int, str, str]] = [
    (10, "view_slides", "View Session Slides"),
    (20, "download_slides", "Download Session Slides"),
    (30, "smart_matches", "Smart Matches"),
    (40, "premium_groups", "Premium Groups Access"),
    (50, "digital_certificate", "Digital Certificate"),
]


def get_unlocked_features(total_points: int) -> list[str]:
    """Return list of feature keys unlocked at the given point total."""
    return [key for threshold, key, _ in MILESTONE_THRESHOLDS if total_points >= threshold]


def compute_tier(total_points: int) -> str:
    """Compute user tier based on total points."""
    if total_points >= 50:
        return "master"
    elif total_points >= 30:
        return "innovator"
    return "explorer"


def award_points(
    db: DBSession,
    user_id: int,
    action_type: str,
    points: int | None = None,
    source_ref: str = "0",
) -> dict | None:
    """
    Award points to a user for a specific action.

    If points is None, look up the action_type in AppConfig "reward_points"
    (falling back to the hardcoded ACTION_POINTS dict).

    Returns a dict with points_added, new_total, and newly unlocked features.
    Returns None if this exact award was already granted (duplicate prevention).

    Does NOT commit — caller must call db.commit().
    """
    # Resolve points from config if not explicitly provided
    if points is None:
        dynamic_points = get_config_value(db, "reward_points", ACTION_POINTS)
        points = dynamic_points.get(action_type, ACTION_POINTS.get(action_type, 0))

    # Check for duplicate award
    existing = (
        db.query(PointTransaction)
        .filter(
            PointTransaction.user_id == user_id,
            PointTransaction.action_type == action_type,
            PointTransaction.source_ref == source_ref,
        )
        .first()
    )
    if existing:
        return None

    # Create transaction record
    txn = PointTransaction(
        user_id=user_id,
        action_type=action_type,
        points_amount=points,
        source_ref=source_ref,
    )
    db.add(txn)

    # Increment user points
    user = db.get(User, user_id)
    if not user:
        return None

    old_total = user.points or 0
    user.points = old_total + points
    new_total = user.points

    db.flush()

    # Determine newly unlocked features
    old_features = set(get_unlocked_features(old_total))
    new_features = set(get_unlocked_features(new_total))
    newly_unlocked = sorted(new_features - old_features)

    return {
        "points_added": points,
        "new_total": new_total,
        "unlocked_features": newly_unlocked,
    }
