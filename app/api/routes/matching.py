from datetime import datetime, timezone, timedelta, date, time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import OnboardingStatus, UserRole, MeetingStatus
from app.models.user import User
from app.models.user_interest import UserInterest
from app.models.interest import Interest
from app.models.user_onboarding import UserOnboarding
from app.models.user_goal import UserGoal
from app.models.goal import Goal
from app.models.group_member import GroupMember
from app.models.group import Group
from app.models.user_agenda import UserAgenda
from app.models.session import Session as ProgramSession
from app.models.meeting import Meeting
from app.services.config_reader import get_config_value
from app.core.blocking import get_blocked_user_ids
from app.api.schemas import MatchedUserOut, SessionBriefOut

router = APIRouter(dependencies=[require_feature("networking")])

# Festival schedule config defaults (same as scheduling.py)
FESTIVAL_START = date(2026, 5, 20)
FESTIVAL_END = date(2026, 5, 24)
MEETING_SLOT_START = time(9, 0)
MEETING_SLOT_END = time(18, 0)
SLOT_DURATION_MINUTES = 30

DEFAULT_SCHEDULE_CONFIG = {
    "festival_start": "2026-05-20",
    "festival_end": "2026-05-24",
    "slot_start_hour": 9,
    "slot_start_minute": 0,
    "slot_end_hour": 18,
    "slot_end_minute": 0,
    "slot_duration_minutes": 30,
    "meeting_hold_minutes": 120,
}

DEFAULT_MATCHING_WEIGHTS = {
    "max_interest_points": 40,
    "complementary_role_points": 30,
    "same_role_points": 10,
    "points_per_group": 5,
    "max_group_points": 20,
    "points_per_session": 2,
    "max_session_points": 10,
}


def _get_matching_weights(db: Session) -> dict:
    """Load matching weights from AppConfig, falling back to defaults."""
    return get_config_value(db, "matching_weights", DEFAULT_MATCHING_WEIGHTS)


def _get_user_busy_times(
    db: Session,
    user_id: int,
    day: date
) -> List[tuple[datetime, datetime]]:
    """
    Get all busy time ranges for a user on a specific day.
    Combines: agenda sessions + confirmed/pending meetings.
    """
    busy_times = []

    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(day, time.max, tzinfo=timezone.utc)

    # Sessions from user's agenda
    agenda_sessions = (
        db.query(ProgramSession)
        .join(UserAgenda)
        .filter(
            UserAgenda.user_id == user_id,
            ProgramSession.start_time >= day_start,
            ProgramSession.start_time <= day_end,
        )
        .all()
    )
    for session in agenda_sessions:
        busy_times.append((session.start_time, session.end_time))

    # Confirmed/pending meetings
    meetings = (
        db.query(Meeting)
        .filter(
            or_(
                Meeting.requester_id == user_id,
                Meeting.recipient_id == user_id,
            ),
            Meeting.status.in_([MeetingStatus.pending, MeetingStatus.confirmed]),
            Meeting.proposed_start >= day_start,
            Meeting.proposed_start <= day_end,
        )
        .all()
    )
    for meeting in meetings:
        busy_times.append((meeting.proposed_start, meeting.proposed_end))

    return busy_times


def _is_user_available_in_window(
    db: Session,
    user_id: int,
    window_start: datetime,
    window_end: datetime,
    slot_start_time: time = MEETING_SLOT_START,
    slot_end_time: time = MEETING_SLOT_END,
    slot_duration: int = SLOT_DURATION_MINUTES,
) -> bool:
    """
    Check if a user has at least one free slot within the given time window.
    """
    day = window_start.date()

    meeting_day_start = datetime.combine(day, slot_start_time, tzinfo=timezone.utc)
    meeting_day_end = datetime.combine(day, slot_end_time, tzinfo=timezone.utc)

    effective_start = max(window_start, meeting_day_start)
    effective_end = min(window_end, meeting_day_end)

    if effective_start >= effective_end:
        return False

    busy_times = _get_user_busy_times(db, user_id, day)

    current = effective_start
    while current + timedelta(minutes=slot_duration) <= effective_end:
        slot_end = current + timedelta(minutes=slot_duration)
        is_busy = False

        for busy_start, busy_end in busy_times:
            if current < busy_end and slot_end > busy_start:
                is_busy = True
                break

        if not is_busy:
            return True

        current += timedelta(minutes=slot_duration)

    return False

# Scoring constants (defaults, overridden by config)
MAX_INTEREST_POINTS = 40
COMPLEMENTARY_ROLE_POINTS = 30  # speaker-exhibitor pairing
SAME_ROLE_POINTS = 10
POINTS_PER_GROUP = 5
MAX_GROUP_POINTS = 20
POINTS_PER_SESSION = 2
MAX_SESSION_POINTS = 10

# Complementary role pairs (like startup-investor)
COMPLEMENTARY_ROLES = {
    (UserRole.speaker, UserRole.exhibitor),
    (UserRole.exhibitor, UserRole.speaker),
}


def _calculate_interest_score(common_count: int, my_total: int, max_points: int = MAX_INTEREST_POINTS) -> float:
    """
    Calculate interest score (up to max_points).
    Score is proportional to common interests vs user's total interests.
    """
    if my_total == 0:
        return 0.0
    ratio = common_count / my_total
    return min(ratio * max_points, max_points)


def _calculate_role_score(
    my_role: UserRole,
    other_role: UserRole,
    complementary_points: int = COMPLEMENTARY_ROLE_POINTS,
    same_points: int = SAME_ROLE_POINTS,
) -> float:
    """
    Calculate role score:
    - complementary_points for complementary roles (speaker-exhibitor)
    - same_points for same role
    """
    if (my_role, other_role) in COMPLEMENTARY_ROLES:
        return complementary_points
    if my_role == other_role:
        return same_points
    return 0.0


def _calculate_group_score(
    common_group_count: int,
    per_group: int = POINTS_PER_GROUP,
    max_points: int = MAX_GROUP_POINTS,
) -> float:
    """
    Calculate group score (up to max_points).
    per_group points per common group.
    """
    return min(common_group_count * per_group, max_points)


def _calculate_session_score(
    common_session_count: int,
    per_session: int = POINTS_PER_SESSION,
    max_points: int = MAX_SESSION_POINTS,
) -> float:
    """
    Calculate session/program score (up to max_points).
    per_session points per common session.
    """
    return min(common_session_count * per_session, max_points)


@router.get("/matching", response_model=list[MatchedUserOut], tags=["matching"])
def get_matching_users(
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    interests: Optional[List[int]] = Query(None, description="Filter by interest IDs (users with ANY of these interests)"),
    available_now: bool = Query(False, description="Filter users available for meeting now (±1 hour)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the top 30 users ranked by matching score.

    Scoring system (0-100+, can exceed 100):
    1. Common Interests: up to 40 points
    2. Roles: speaker-exhibitor = 30 points, same role = 10 points
    3. Groups: 5 points per common group (up to 20)
    4. Common Program: 2 points per common session (up to 10)

    Only includes users who have completed onboarding.

    Optional filters:
    - role: Filter by user role (attendee, speaker, exhibitor, admin)
    - interests: Filter by interest IDs (users with ANY of these interests)
    - available_now: Only return users available for meeting in the next ±1 hour
    """
    # Check if current user has completed onboarding
    my_onboarding = db.query(UserOnboarding).filter(
        UserOnboarding.user_id == current_user.id,
        UserOnboarding.status == OnboardingStatus.completed,
    ).first()

    if not my_onboarding:
        raise HTTPException(
            status_code=400,
            detail="You must complete onboarding before using matching.",
        )

    # Load config
    weights = _get_matching_weights(db)
    sched_cfg = get_config_value(db, "schedule_config", DEFAULT_SCHEDULE_CONFIG)

    # Get the current user's data
    my_interest_ids = set(
        row[0] for row in db.query(UserInterest.interest_id)
        .filter(UserInterest.user_id == current_user.id)
        .all()
    )

    my_goal_ids = set(
        row[0] for row in db.query(UserGoal.goal_id)
        .filter(UserGoal.user_id == current_user.id)
        .all()
    )

    my_group_ids = set(
        row[0] for row in db.query(GroupMember.group_id)
        .filter(GroupMember.user_id == current_user.id)
        .all()
    )

    my_session_ids = set(
        row[0] for row in db.query(UserAgenda.session_id)
        .filter(UserAgenda.user_id == current_user.id)
        .all()
    )

    my_discussion_topics = set(my_onboarding.discussion_topics or [])
    my_experience_level = my_onboarding.experience_level

    # Get user IDs who have completed onboarding (excluding current user)
    completed_onboardings = (
        db.query(UserOnboarding)
        .filter(
            UserOnboarding.status == OnboardingStatus.completed,
            UserOnboarding.user_id != current_user.id,
        )
        .all()
    )

    if not completed_onboardings:
        return []

    completed_user_ids = [ob.user_id for ob in completed_onboardings]
    onboarding_map = {ob.user_id: ob for ob in completed_onboardings}

    # Filter out blocked users
    blocked_ids = get_blocked_user_ids(db, current_user.id)
    completed_user_ids = [uid for uid in completed_user_ids if uid not in blocked_ids]

    if not completed_user_ids:
        return []

    # Get all candidate users with optional role filter
    candidate_query = db.query(User).filter(User.id.in_(completed_user_ids))

    if role is not None:
        candidate_query = candidate_query.filter(User.role == role)

    candidate_users = candidate_query.all()

    # Apply interests filter if provided
    if interests:
        users_with_interests = set(
            row[0] for row in db.query(UserInterest.user_id)
            .filter(
                UserInterest.user_id.in_([u.id for u in candidate_users]),
                UserInterest.interest_id.in_(interests)
            )
            .distinct()
            .all()
        )
        candidate_users = [u for u in candidate_users if u.id in users_with_interests]

    # Apply available_now filter if requested
    if available_now:
        now = datetime.now(timezone.utc)
        today = now.date()

        # Check if today is within festival dates (from config)
        cfg_fest_start = date.fromisoformat(sched_cfg.get("festival_start", "2026-05-20"))
        cfg_fest_end = date.fromisoformat(sched_cfg.get("festival_end", "2026-05-24"))
        if today < cfg_fest_start or today > cfg_fest_end:
            return []

        cfg_slot_start = time(sched_cfg.get("slot_start_hour", 9), sched_cfg.get("slot_start_minute", 0))
        cfg_slot_end = time(sched_cfg.get("slot_end_hour", 18), sched_cfg.get("slot_end_minute", 0))
        cfg_slot_dur = sched_cfg.get("slot_duration_minutes", 30)

        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        candidate_users = [
            u for u in candidate_users
            if _is_user_available_in_window(
                db, u.id, window_start, window_end,
                slot_start_time=cfg_slot_start,
                slot_end_time=cfg_slot_end,
                slot_duration=cfg_slot_dur,
            )
        ]

    if not candidate_users:
        return []

    # Update completed_user_ids to reflect filtered candidates
    completed_user_ids = [u.id for u in candidate_users]
    user_map = {u.id: u for u in candidate_users}

    # Get interests for all candidates
    candidate_interests = (
        db.query(UserInterest.user_id, UserInterest.interest_id)
        .filter(UserInterest.user_id.in_(completed_user_ids))
        .all()
    )
    interests_by_user: dict[int, set[int]] = {}
    for user_id, interest_id in candidate_interests:
        interests_by_user.setdefault(user_id, set()).add(interest_id)

    # Get goals for all candidates
    candidate_goals = (
        db.query(UserGoal.user_id, UserGoal.goal_id)
        .filter(UserGoal.user_id.in_(completed_user_ids))
        .all()
    )
    goals_by_user: dict[int, set[int]] = {}
    for user_id, goal_id in candidate_goals:
        goals_by_user.setdefault(user_id, set()).add(goal_id)

    # Get groups for all candidates
    candidate_groups = (
        db.query(GroupMember.user_id, GroupMember.group_id)
        .filter(GroupMember.user_id.in_(completed_user_ids))
        .all()
    )
    groups_by_user: dict[int, set[int]] = {}
    for user_id, group_id in candidate_groups:
        groups_by_user.setdefault(user_id, set()).add(group_id)

    # Get sessions (agenda) for all candidates
    candidate_sessions = (
        db.query(UserAgenda.user_id, UserAgenda.session_id)
        .filter(UserAgenda.user_id.in_(completed_user_ids))
        .all()
    )
    sessions_by_user: dict[int, set[int]] = {}
    for user_id, session_id in candidate_sessions:
        sessions_by_user.setdefault(user_id, set()).add(session_id)

    # Calculate scores for all candidates
    scored_candidates = []
    for user_id in completed_user_ids:
        user = user_map.get(user_id)
        if not user:
            continue

        onboarding = onboarding_map.get(user_id)
        if not onboarding:
            continue

        # Calculate common items
        other_interests = interests_by_user.get(user_id, set())
        common_interest_ids = my_interest_ids & other_interests

        other_goals = goals_by_user.get(user_id, set())
        common_goal_ids = my_goal_ids & other_goals

        other_groups = groups_by_user.get(user_id, set())
        common_group_ids = my_group_ids & other_groups

        other_sessions = sessions_by_user.get(user_id, set())
        common_session_ids = my_session_ids & other_sessions

        other_discussion_topics = set(onboarding.discussion_topics or [])
        common_topics = my_discussion_topics & other_discussion_topics

        # Check if same experience level
        same_level = (
            my_experience_level is not None
            and onboarding.experience_level is not None
            and my_experience_level == onboarding.experience_level
        )

        # Calculate score components using config weights
        interest_score = _calculate_interest_score(
            len(common_interest_ids),
            len(my_interest_ids),
            max_points=weights.get("max_interest_points", MAX_INTEREST_POINTS),
        )
        role_score = _calculate_role_score(
            current_user.role, user.role,
            complementary_points=weights.get("complementary_role_points", COMPLEMENTARY_ROLE_POINTS),
            same_points=weights.get("same_role_points", SAME_ROLE_POINTS),
        )
        group_score = _calculate_group_score(
            len(common_group_ids),
            per_group=weights.get("points_per_group", POINTS_PER_GROUP),
            max_points=weights.get("max_group_points", MAX_GROUP_POINTS),
        )
        session_score = _calculate_session_score(
            len(common_session_ids),
            per_session=weights.get("points_per_session", POINTS_PER_SESSION),
            max_points=weights.get("max_session_points", MAX_SESSION_POINTS),
        )

        total_score = interest_score + role_score + group_score + session_score

        scored_candidates.append({
            "user_id": user_id,
            "user": user,
            "common_interest_ids": common_interest_ids,
            "common_goal_ids": common_goal_ids,
            "common_group_ids": common_group_ids,
            "common_topics": common_topics,
            "same_level": same_level,
            "total_score": total_score,
        })

    # Sort by score descending and take top 30
    scored_candidates.sort(key=lambda x: x["total_score"], reverse=True)
    top_matches = scored_candidates[:30]

    if not top_matches:
        return []

    # Get all interest names (for both common and all user interests)
    all_interest_ids = set()
    for match in top_matches:
        all_interest_ids.update(match["common_interest_ids"])
        all_interest_ids.update(interests_by_user.get(match["user_id"], set()))

    interest_names = {}
    if all_interest_ids:
        interests = (
            db.query(Interest.id, Interest.name)
            .filter(Interest.id.in_(all_interest_ids))
            .all()
        )
        interest_names = {i[0]: i[1] for i in interests}

    # Get goal names for common goals
    all_common_goal_ids = set()
    for match in top_matches:
        all_common_goal_ids.update(match["common_goal_ids"])

    goal_names = {}
    if all_common_goal_ids:
        goals = (
            db.query(Goal.id, Goal.name)
            .filter(Goal.id.in_(all_common_goal_ids))
            .all()
        )
        goal_names = {g[0]: g[1] for g in goals}

    # Get group names for common groups
    all_common_group_ids = set()
    for match in top_matches:
        all_common_group_ids.update(match["common_group_ids"])

    group_names = {}
    if all_common_group_ids:
        groups = (
            db.query(Group.id, Group.title)
            .filter(Group.id.in_(all_common_group_ids))
            .all()
        )
        group_names = {g[0]: g[1] for g in groups}

    # Get sessions for speakers in top matches
    from sqlalchemy.orm import joinedload
    from app.core.enums import UserRole as UR
    speaker_ids = [m["user_id"] for m in top_matches if m["user"].role == UR.speaker]
    sessions_by_speaker: dict[int, list] = {}
    if speaker_ids:
        speaker_sessions = (
            db.query(ProgramSession)
            .join(ProgramSession.speakers)
            .options(joinedload(ProgramSession.venue))
            .filter(User.id.in_(speaker_ids))
            .order_by(ProgramSession.start_time)
            .all()
        )
        for session in speaker_sessions:
            for speaker in session.speakers:
                if speaker.id in speaker_ids:
                    sessions_by_speaker.setdefault(speaker.id, []).append(session)

    # Build result
    result = []
    for match in top_matches:
        user = match["user"]
        user_id = match["user_id"]

        # Common interest names
        common_interest_names = [
            interest_names[iid]
            for iid in match["common_interest_ids"]
            if iid in interest_names
        ]

        # All interest names for this user
        all_user_interest_names = [
            interest_names[iid]
            for iid in interests_by_user.get(user_id, set())
            if iid in interest_names
        ]

        common_goal_names = [
            goal_names[gid]
            for gid in match["common_goal_ids"]
            if gid in goal_names
        ]

        common_group_names = [
            group_names[gid]
            for gid in match["common_group_ids"]
            if gid in group_names
        ]

        # Sessions for speakers
        sessions_out = None
        if user.role == UR.speaker and user_id in sessions_by_speaker:
            sessions_out = [
                SessionBriefOut(
                    id=s.id,
                    title=s.title,
                    start_time=s.start_time.isoformat(),
                    end_time=s.end_time.isoformat(),
                    type=s.type,
                    venue_name=s.venue.name if s.venue else None,
                )
                for s in sessions_by_speaker[user_id]
            ]

        result.append(
            MatchedUserOut(
                user_id=user_id,
                full_name=user.full_name,
                role=user.role.value if hasattr(user.role, 'value') else str(user.role),
                company=user.company,
                bio=user.bio,
                avatar_url=user.avatar_url,
                linkedin_url=user.linkedin_url,
                interests=all_user_interest_names or None,
                sessions=sessions_out,
                common_interests=common_interest_names,
                common_goals=common_goal_names,
                common_groups=common_group_names,
                common_discussion_topics=list(match["common_topics"]),
                same_level=match["same_level"],
                match_score=round(match["total_score"], 1),
            )
        )

    return result
