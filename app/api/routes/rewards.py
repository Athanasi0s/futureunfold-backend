"""
Rewards API routes — user points, milestones, profile wrap-up, leaderboard.

Endpoints:
- GET /rewards/me              → current user's points, tier, unlocked features, recent txns
- GET /rewards/milestones      → milestone definitions with user's progress
- GET /rewards/profile-wrapup  → stats + timeline for the "Festival Wrap-up" view
- GET /rewards/leaderboard     → top users by points
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.point_transaction import PointTransaction
from app.models.user_agenda import UserAgenda
from app.models.group_member import GroupMember
from app.models.scan_log import ScanLog
from app.models.session import Session as SessionModel
from app.services.rewards import (
    MILESTONE_THRESHOLDS,
    ACTION_CATALOG,
    get_unlocked_features,
    compute_tier,
)
from app.services.leaderboard import (
    get_enhanced_leaderboard,
    get_my_stats,
)
from app.api.schemas import (
    RewardsMeOut,
    PointTransactionOut,
    MilestoneOut,
    ProfileWrapUpOut,
    LeaderboardEntryOut,
    EarnActionOut,
    EnhancedLeaderboardOut,
    LeaderboardCategoryEntryOut,
    LeaderboardStatsOut,
    JourneyTimelineOut,
    CertificateDataOut,
)
from app.services.journey import get_journey_timeline
from app.services.certification import compute_milestones
from app.services.config_reader import get_config_value

router = APIRouter(dependencies=[require_feature("rewards")])


# ──────────────────────────────────────
# GET /rewards/actions — public earning-actions catalogue
# ──────────────────────────────────────
@router.get("/rewards/actions", response_model=list[EarnActionOut])
def list_earning_actions():
    """Επιστρέφει τον κατάλογο ενεργειών που δίνουν πόντους (How to Earn)."""
    return [EarnActionOut(**entry) for entry in ACTION_CATALOG]


# ──────────────────────────────────────
# GET /rewards/me — points, tier, unlocks, recent transactions
# ──────────────────────────────────────
@router.get("/rewards/me", response_model=RewardsMeOut)
def get_my_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει τα reward data του τρέχοντα χρήστη."""
    total = current_user.points or 0

    transactions = (
        db.query(PointTransaction)
        .filter(PointTransaction.user_id == current_user.id)
        .order_by(PointTransaction.created_at.desc())
        .limit(20)
        .all()
    )

    return RewardsMeOut(
        total_points=total,
        current_tier=compute_tier(total),
        unlocked_features=get_unlocked_features(total),
        recent_transactions=[
            PointTransactionOut(
                id=t.id,
                action_type=t.action_type,
                points_amount=t.points_amount,
                source_ref=t.source_ref,
                created_at=t.created_at.isoformat(),
            )
            for t in transactions
        ],
    )


# ──────────────────────────────────────
# GET /rewards/milestones — milestone checklist
# ──────────────────────────────────────
@router.get("/rewards/milestones", response_model=list[MilestoneOut])
def get_milestones(
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει τα milestones με πληροφορία αν έχουν επιτευχθεί."""
    total = current_user.points or 0

    return [
        MilestoneOut(
            threshold=threshold,
            feature_key=key,
            label=label,
            achieved=total >= threshold,
        )
        for threshold, key, label in MILESTONE_THRESHOLDS
    ]


# ──────────────────────────────────────
# GET /rewards/profile-wrapup — festival stats & timeline
# ──────────────────────────────────────
@router.get("/rewards/profile-wrapup", response_model=ProfileWrapUpOut, dependencies=[require_feature("certificates")])
def get_profile_wrapup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει τα στατιστικά του χρήστη για το Profile Wrap-up view."""
    total = current_user.points or 0

    # Percentile rank
    total_users = db.query(sa_func.count(User.id)).scalar() or 1
    users_below = (
        db.query(sa_func.count(User.id)).filter(User.points < total).scalar() or 0
    )
    percentile = round((users_below / total_users) * 100, 1)

    # Stats
    sessions_attended = (
        db.query(sa_func.count(UserAgenda.id))
        .filter(UserAgenda.user_id == current_user.id)
        .scalar()
        or 0
    )
    groups_joined = (
        db.query(sa_func.count(GroupMember.id))
        .filter(GroupMember.user_id == current_user.id)
        .scalar()
        or 0
    )
    total_scans = (
        db.query(sa_func.count(ScanLog.id))
        .filter(
            (ScanLog.scanner_id == current_user.id)
            | (ScanLog.scanned_id == current_user.id)
        )
        .scalar()
        or 0
    )

    # Total hours from agenda sessions
    agenda_sessions = (
        db.query(SessionModel)
        .join(UserAgenda, UserAgenda.session_id == SessionModel.id)
        .filter(UserAgenda.user_id == current_user.id)
        .all()
    )
    total_hours = round(
        sum(
            (s.end_time - s.start_time).total_seconds() / 3600
            for s in agenda_sessions
        ),
        1,
    )

    # Milestone timeline (all point transactions, chronological)
    transactions = (
        db.query(PointTransaction)
        .filter(PointTransaction.user_id == current_user.id)
        .order_by(PointTransaction.created_at.asc())
        .all()
    )

    # Greeting
    name = current_user.full_name or "Explorer"
    top_pct = max(1, round(100 - percentile))
    greeting = f"Great Journey, {name}! Top {top_pct}% of explorers"

    return ProfileWrapUpOut(
        greeting=greeting,
        percentile_rank=percentile,
        sessions_attended=sessions_attended,
        total_hours=total_hours,
        groups_joined=groups_joined,
        total_scans=total_scans,
        milestone_timeline=[
            PointTransactionOut(
                id=t.id,
                action_type=t.action_type,
                points_amount=t.points_amount,
                source_ref=t.source_ref,
                created_at=t.created_at.isoformat(),
            )
            for t in transactions
        ],
        certificate_eligible=total >= 50,
    )


# ──────────────────────────────────────
# GET /rewards/leaderboard — top users by points
# ──────────────────────────────────────
@router.get("/rewards/leaderboard", response_model=list[LeaderboardEntryOut], dependencies=[require_feature("leaderboard")])
def get_rewards_leaderboard(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """Επιστρέφει τους χρήστες με τους περισσότερους πόντους."""
    users = (
        db.query(User)
        .filter(User.points > 0)
        .order_by(User.points.desc())
        .limit(limit)
        .all()
    )

    return [
        LeaderboardEntryOut(
            user_id=u.id,
            full_name=u.full_name,
            role=u.role.value if u.role else "attendee",
            points=u.points or 0,
            rank=idx + 1,
        )
        for idx, u in enumerate(users)
    ]


# ──────────────────────────────────────
# GET /rewards/leaderboard/enhanced — multi-category leaderboard
# ──────────────────────────────────────
@router.get("/rewards/leaderboard/enhanced", response_model=EnhancedLeaderboardOut, dependencies=[require_feature("leaderboard")])
def get_enhanced_leaderboard_endpoint(
    category: str = Query("points", pattern="^(points|sessions|groups|scans)$"),
    period: str = Query("all_time", pattern="^(all_time|daily)$"),
    date_param: Optional[str] = Query(None, alias="date"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enhanced leaderboard with 4 categories, all-time/daily periods, and user stats."""
    # Parse date param
    target_date = None
    if period == "daily":
        if date_param:
            try:
                target_date = date.fromisoformat(date_param)
            except ValueError:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        else:
            target_date = date.today()

    entries, my_entry = get_enhanced_leaderboard(
        db, category, period, target_date, limit, current_user.id,
    )

    # Build my_stats (all-time ranks across all categories)
    stats_dict = get_my_stats(db, current_user.id)
    my_stats = LeaderboardStatsOut(**stats_dict)

    # Convert dicts to schema objects
    entry_models = [LeaderboardCategoryEntryOut(**e) for e in entries]
    my_entry_model = LeaderboardCategoryEntryOut(**my_entry) if my_entry else None

    return EnhancedLeaderboardOut(
        entries=entry_models,
        my_entry=my_entry_model,
        my_stats=my_stats,
        category=category,
        period=period,
        date=date_param if period == "daily" else None,
    )


# ──────────────────────────────────────
# GET /rewards/journey-timeline — chronological activity feed
# ──────────────────────────────────────
@router.get("/rewards/journey-timeline", response_model=JourneyTimelineOut, dependencies=[require_feature("certificates")])
def get_journey_timeline_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει χρονολογικό timeline δραστηριοτήτων του χρήστη στο φεστιβάλ."""
    return get_journey_timeline(db, current_user.id)


# ──────────────────────────────────────
# GET /rewards/certificate-data — certificate milestones + template
# ──────────────────────────────────────
_DEFAULT_CERTIFICATE_TEMPLATE = {
    "version": 1,
    "festival_name": "Panathenea 2026",
    "tagline": "Innovation Meets Tradition",
    "logo_url": None,
    "primary_color": "#194ff0",
    "secondary_color": "#101522",
    "accent_color": "#10b981",
    "background_gradient": ["#101522", "#1a2744"],
    "border_color": "#2a3a6a",
}


@router.get("/rewards/certificate-data", response_model=CertificateDataOut, dependencies=[require_feature("certificates")])
def get_certificate_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει δεδομένα πιστοποιητικού: milestones, ranks, template config."""
    template = get_config_value(db, "certificate_template", _DEFAULT_CERTIFICATE_TEMPLATE)
    template_version = template.get("version", 1) if isinstance(template, dict) else 1

    # Read milestone_titles from template config and pass to compute_milestones
    milestone_titles = template.get("milestone_titles", {}) if isinstance(template, dict) else {}
    all_milestones = compute_milestones(db, current_user.id, custom_titles=milestone_titles)
    top_milestones = all_milestones[:3]

    # Ensure orientation is included in template response (preserve from config, default landscape)
    if isinstance(template, dict) and "orientation" not in template:
        template = {**template, "orientation": "landscape"}

    return CertificateDataOut(
        user_name=current_user.full_name or "Festival Explorer",
        user_avatar_url=current_user.avatar_url if hasattr(current_user, "avatar_url") else None,
        top_milestones=top_milestones,
        all_milestones=all_milestones,
        template=template,
        template_version=template_version,
    )
