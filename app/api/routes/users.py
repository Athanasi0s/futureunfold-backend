from datetime import datetime, timezone, timedelta, date, time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload, Session

from app.core.deps import get_db, get_optional_current_user, get_current_user
from app.core.enums import UserRole, MeetingStatus
from app.models.user import User
from app.models.session import Session as SessionModel
from app.models.user_interest import UserInterest
from app.models.interest import Interest
from app.models.user_agenda import UserAgenda
from app.models.meeting import Meeting
from app.models.group import Group
from app.models.group_member import GroupMember
from pydantic import BaseModel as PydanticBaseModel
from app.models.app_config import AppConfig
from app.core.blocking import get_blocked_user_ids
from app.api.schemas import UserProfileOut, SessionBriefOut, UsersListOut, UserListItemOut, GroupOut, AgendaItemOut, SessionOut

router = APIRouter()

# Festival schedule config (same as scheduling.py)
FESTIVAL_START = date(2026, 5, 20)
FESTIVAL_END = date(2026, 5, 24)
MEETING_SLOT_START = time(9, 0)
MEETING_SLOT_END = time(18, 0)
SLOT_DURATION_MINUTES = 30


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

    # Day boundaries (UTC)
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(day, time.max, tzinfo=timezone.utc)

    # 1. Get sessions from user's agenda
    agenda_query = (
        select(SessionModel)
        .join(UserAgenda)
        .where(
            UserAgenda.user_id == user_id,
            SessionModel.start_time >= day_start,
            SessionModel.start_time <= day_end,
        )
    )
    sessions = db.execute(agenda_query).scalars().all()
    for session in sessions:
        busy_times.append((session.start_time, session.end_time))

    # 2. Get confirmed/pending meetings (as requester or recipient)
    meetings_query = (
        select(Meeting)
        .where(
            or_(
                Meeting.requester_id == user_id,
                Meeting.recipient_id == user_id,
            ),
            Meeting.status.in_([MeetingStatus.pending, MeetingStatus.confirmed]),
            Meeting.proposed_start >= day_start,
            Meeting.proposed_start <= day_end,
        )
    )
    meetings = db.execute(meetings_query).scalars().all()
    for meeting in meetings:
        busy_times.append((meeting.proposed_start, meeting.proposed_end))

    return busy_times


def _is_user_available_in_window(
    db: Session,
    user_id: int,
    window_start: datetime,
    window_end: datetime
) -> bool:
    """
    Check if a user has at least one free 30-minute slot within the given time window.
    """
    day = window_start.date()

    # Clamp window to festival meeting hours
    meeting_day_start = datetime.combine(day, MEETING_SLOT_START, tzinfo=timezone.utc)
    meeting_day_end = datetime.combine(day, MEETING_SLOT_END, tzinfo=timezone.utc)

    effective_start = max(window_start, meeting_day_start)
    effective_end = min(window_end, meeting_day_end)

    # If window is outside meeting hours, no availability
    if effective_start >= effective_end:
        return False

    busy_times = _get_user_busy_times(db, user_id, day)

    # Check each 30-minute slot in the window
    current = effective_start
    while current + timedelta(minutes=SLOT_DURATION_MINUTES) <= effective_end:
        slot_end = current + timedelta(minutes=SLOT_DURATION_MINUTES)
        is_busy = False

        for busy_start, busy_end in busy_times:
            # Overlap check
            if current < busy_end and slot_end > busy_start:
                is_busy = True
                break

        if not is_busy:
            return True  # Found a free slot

        current += timedelta(minutes=SLOT_DURATION_MINUTES)

    return False


@router.get("/users", response_model=UsersListOut)
def get_users(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    search: Optional[str] = Query(None, description="Search users by full name (case-insensitive)"),
    interests: Optional[List[int]] = Query(None, description="Filter by interest IDs (users with ANY of these interests)"),
    available_now: bool = Query(False, description="Filter users available for meeting now (±1 hour)"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Get paginated list of users with optional filtering by role, interests, and availability."""
    # Base query
    query = select(User)

    # Filter out blocked users when authenticated
    blocked_ids = get_blocked_user_ids(db, current_user.id) if current_user else set()
    if blocked_ids:
        query = query.where(~User.id.in_(blocked_ids))

    # Apply role filter if provided
    if role is not None:
        query = query.where(User.role == role)

    # Apply search filter on full_name
    if search:
        query = query.where(User.full_name.ilike(f"%{search}%"))

    # Apply interests filter if provided (users with ANY of the specified interests)
    if interests:
        # Subquery to find user_ids that have any of the specified interests
        interest_subquery = (
            select(UserInterest.user_id)
            .where(UserInterest.interest_id.in_(interests))
            .distinct()
        )
        query = query.where(User.id.in_(interest_subquery))

    # If available_now is requested, we need to filter after fetching
    # because availability check requires per-user busy time calculation
    if available_now:
        now = datetime.now(timezone.utc)
        today = now.date()

        # Check if today is within festival dates
        if today < FESTIVAL_START or today > FESTIVAL_END:
            # Outside festival dates - no one is "available for meetings"
            return UsersListOut(
                users=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=1,
            )

        # Define ±1 hour window
        window_start = now - timedelta(hours=1)
        window_end = now + timedelta(hours=1)

        # Fetch ALL matching users first (without pagination)
        all_users = db.execute(query.order_by(User.id)).scalars().all()

        # Filter by availability
        available_users = [
            u for u in all_users
            if _is_user_available_in_window(db, u.id, window_start, window_end)
        ]

        total = len(available_users)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        offset = (page - 1) * page_size

        # Apply pagination manually
        users = available_users[offset:offset + page_size]
    else:
        # Count query (matches filters applied above)
        count_query = select(func.count(User.id))
        if blocked_ids:
            count_query = count_query.where(~User.id.in_(blocked_ids))
        if role is not None:
            count_query = count_query.where(User.role == role)
        if interests:
            interest_subquery = (
                select(UserInterest.user_id)
                .where(UserInterest.interest_id.in_(interests))
                .distinct()
            )
            count_query = count_query.where(User.id.in_(interest_subquery))

        total = db.execute(count_query).scalar()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        offset = (page - 1) * page_size

        # Fetch users with pagination
        query = query.order_by(User.id).offset(offset).limit(page_size)
        users = db.execute(query).scalars().all()

    # Fetch interests for all users in this page
    user_ids = [u.id for u in users]
    if user_ids:
        interests_query = (
            select(UserInterest.user_id, Interest.name)
            .join(Interest, Interest.id == UserInterest.interest_id)
            .where(UserInterest.user_id.in_(user_ids))
        )
        interests_rows = db.execute(interests_query).all()
    else:
        interests_rows = []

    # Group interests by user_id
    user_interests: dict[int, list[str]] = {}
    for user_id, interest_name in interests_rows:
        user_interests.setdefault(user_id, []).append(interest_name)

    # Build response
    users_out = [
        UserListItemOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value if hasattr(u.role, 'value') else str(u.role),
            company=u.company,
            bio=u.bio,
            avatar_url=u.avatar_url,
            linkedin_url=u.linkedin_url,
            interests=user_interests.get(u.id, []),
        )
        for u in users
    ]

    return UsersListOut(
        users=users_out,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=UserProfileOut)
def get_user_profile(user_id: int, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_current_user)):
    # Fetch user
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Ο χρήστης δεν βρέθηκε.")

    # Interests (names)
    interests_query = (
        select(Interest.name)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .where(UserInterest.user_id == user_id)
    )
    interests = [row[0] for row in db.execute(interests_query).all()]

    # Sessions (only if user is a speaker)
    sessions_out = None
    if user.role == UserRole.speaker:
        sessions_query = (
            select(SessionModel)
            .join(SessionModel.speakers)
            .options(joinedload(SessionModel.venue))
            .where(User.id == user_id)
            .order_by(SessionModel.start_time)
        )
        sessions = db.execute(sessions_query).unique().scalars().all()
        sessions_out = [
            SessionBriefOut(
                id=s.id,
                title=s.title,
                start_time=s.start_time.isoformat(),
                end_time=s.end_time.isoformat(),
                type=s.type,
                venue_name=s.venue.name if s.venue else None,
            )
            for s in sessions
        ]

    # Email visibility: only to the user themself or admins
    email_value = None
    if current_user is not None and (
        getattr(current_user, "id", None) == user_id or getattr(current_user, "role", None) == UserRole.admin
    ):
        email_value = user.email

    return UserProfileOut(
        id=user.id,
        email=email_value,
        full_name=user.full_name or "",
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        company=user.company,
        bio=user.bio,
        avatar_url=user.avatar_url,
        linkedin_url=user.linkedin_url,
        interests=interests or None,
        sessions=sessions_out,
    )


@router.get("/users/{user_id}/common-groups", response_model=List[GroupOut])
def get_common_groups(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get groups that both the authenticated user and the specified user belong to.
    """
    # Check if target user exists
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Ο χρήστης δεν βρέθηκε.")

    # Get group IDs for current user
    current_user_groups = set(
        row[0] for row in db.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == current_user.id)
        ).all()
    )

    # Get group IDs for target user
    target_user_groups = set(
        row[0] for row in db.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == user_id)
        ).all()
    )

    # Find common group IDs
    common_group_ids = current_user_groups & target_user_groups

    if not common_group_ids:
        return []

    # Fetch groups with member counts
    groups = db.execute(
        select(Group).where(Group.id.in_(common_group_ids)).order_by(Group.id)
    ).scalars().all()

    # Get member counts for all groups
    member_counts = dict(
        db.execute(
            select(GroupMember.group_id, func.count(GroupMember.id))
            .where(GroupMember.group_id.in_(common_group_ids))
            .group_by(GroupMember.group_id)
        ).all()
    )

    return [
        GroupOut(
            id=g.id,
            group_type=g.group_type,
            ref_key=g.ref_key,
            title=g.title,
            description=g.description,
            member_count=member_counts.get(g.id, 0),
            match_percentage=None,
        )
        for g in groups
    ]


def _session_to_out(session: SessionModel) -> dict:
    """Convert Session model to SessionOut dict."""
    return {
        "id": session.id,
        "title": session.title,
        "description": session.description,
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat(),
        "type": session.type,
        "topic_tags": session.topic_tags,
        "image_url": session.image_url,
        "venue": session.venue,
        "speakers": [
            {
                "user_id": u.id,
                "full_name": u.full_name or "Unknown",
                "company": u.company,
                "avatar_url": u.avatar_url,
            }
            for u in session.speakers
        ],
    }


@router.get("/users/{user_id}/agenda", response_model=List[AgendaItemOut])
def get_user_agenda(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the program/agenda of a specific user.
    Returns the sessions the user has saved to their agenda, sorted by start_time.
    """
    # Check if target user exists
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Ο χρήστης δεν βρέθηκε.")

    # Get user's agenda with sessions
    query = (
        select(UserAgenda)
        .options(
            joinedload(UserAgenda.session).joinedload(SessionModel.venue),
            joinedload(UserAgenda.session).selectinload(SessionModel.speakers),
        )
        .where(UserAgenda.user_id == user_id)
        .join(SessionModel)
        .order_by(SessionModel.start_time)
    )

    rows = db.execute(query).unique().scalars().all()

    return [
        AgendaItemOut(
            id=item.id,
            session=SessionOut(**_session_to_out(item.session)),
            created_at=item.created_at.isoformat(),
        )
        for item in rows
    ]


class SetThemeIn(PydanticBaseModel):
    theme_id: str | None = None


@router.put("/me/theme")
def set_theme_preference(
    payload: SetThemeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.theme_id is not None:
        config_row = db.get(AppConfig, "user_theme_options")
        allowed = config_row.value if config_row else []
        if payload.theme_id not in allowed:
            raise HTTPException(400, "Theme not available for users")
    current_user.theme_preference = payload.theme_id
    db.commit()
    return {"ok": True, "theme": payload.theme_id}


@router.get("/me/theme")
def get_theme_preference(
    current_user: User = Depends(get_current_user),
):
    return {"theme": current_user.theme_preference}