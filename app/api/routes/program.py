"""
Program & Sessions API routes.

Endpoints:
- GET /program          - List all sessions with filters
- GET /sessions/{id}    - Session detail with slides logic
- GET /speakers         - List all speakers
- GET /speakers/{id}    - Speaker detail with sessions
- GET /my-agenda        - User's saved sessions (auth required)
- POST /sessions/{id}/favorite   - Add to agenda (auth required)
- DELETE /sessions/{id}/favorite - Remove from agenda (auth required)
- GET /exhibitors/{id}/sessions  - Get all sessions by an exhibitor
"""

from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session, selectinload, joinedload

from app.core.deps import get_db, get_current_user, get_optional_current_user, require_feature, require_moderator_scope
from app.models.user import User
from app.services.rewards import award_points
from app.models.session import Session as SessionModel
from app.models.venue import Venue
from app.models.map_feature import MapFeature
from app.models.user_agenda import UserAgenda
from app.models.poll import Poll
from app.models.poll_answer import PollAnswer
from app.core.enums import UserRole
from app.api.schemas import (
    SessionOut,
    SessionDetailOut,
    SessionBriefOut,
    SessionCreateIn,
    SessionUpdateIn,
    SpeakerOut,
    SpeakerBriefOut,
    SpeakerWithSessionsOut,
    AgendaItemOut,
    FavoriteResponseOut,
    PollOut,
    PollOptionOut,
)

router = APIRouter(dependencies=[require_feature("schedule")])


def _user_to_speaker_brief(user: User) -> dict:
    """Convert User (with role='speaker') to brief dict for session responses."""
    return {
        "user_id": user.id,
        "full_name": user.full_name or "Unknown",
        "company": user.company,
        "avatar_url": user.avatar_url,
    }


def _user_to_speaker_full(user: User) -> dict:
    """Convert User (with role='speaker') to full profile dict."""
    return {
        "user_id": user.id,
        "full_name": user.full_name or "Unknown",
        "email": user.email,
        "company": user.company,
        "bio": user.bio,
        "avatar_url": user.avatar_url,
        "linkedin_url": user.linkedin_url,
    }


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
        "speakers": [_user_to_speaker_brief(u) for u in session.speakers],
        "is_cancelled": session.is_cancelled,
        "cancelled_at": session.cancelled_at,
    }


def _session_to_brief(session: SessionModel) -> SessionBriefOut:
    """Convert Session model to SessionBriefOut."""
    return SessionBriefOut(
        id=session.id,
        title=session.title,
        start_time=session.start_time.isoformat(),
        end_time=session.end_time.isoformat(),
        type=session.type,
        venue_name=session.venue.name if session.venue else None,
    )


# -----------------------------
# PUBLIC ENDPOINTS
# -----------------------------


@router.get("/program", response_model=list[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    day: Optional[date] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    topic: Optional[str] = Query(None, description="Filter by topic tag"),
    venue_id: Optional[int] = Query(None, description="Filter by venue ID"),
    search: Optional[str] = Query(None, description="Search in title, description, speaker names"),
):
    """
    Fetch the full program with optional filters.
    Returns sessions sorted by start_time, including speaker and venue info.
    """
    query = (
        select(SessionModel)
        .options(
            joinedload(SessionModel.venue),
            selectinload(SessionModel.speakers),
        )
        .where(SessionModel.is_cancelled.is_(False))
        .order_by(SessionModel.start_time)
    )

    # Filter by day
    if day:
        # Convert date to datetime range for that day (UTC)
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)
        query = query.where(
            and_(
                SessionModel.start_time >= day_start,
                SessionModel.start_time <= day_end,
            )
        )

    # Filter by topic tag
    if topic:
        query = query.where(SessionModel.topic_tags.contains([topic]))

    # Filter by venue
    if venue_id:
        query = query.where(SessionModel.venue_id == venue_id)

    # Text search across title, description, and speaker names
    if search:
        search_term = f"%{search.lower()}%"
        # Subquery to find sessions with matching speakers (via User.full_name)
        speaker_subquery = (
            select(SessionModel.id)
            .join(SessionModel.speakers)
            .where(func.lower(User.full_name).like(search_term))
        )
        query = query.where(
            or_(
                func.lower(SessionModel.title).like(search_term),
                func.lower(SessionModel.description).like(search_term),
                SessionModel.id.in_(speaker_subquery),
            )
        )

    rows = db.execute(query).unique().scalars().all()

    # Convert to response format
    return [_session_to_out(s) for s in rows]


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed session info including slides (if unlocked or session ended).
    """
    query = (
        select(SessionModel)
        .options(
            joinedload(SessionModel.venue),
            selectinload(SessionModel.speakers),
        )
        .where(SessionModel.id == session_id)
        .where(SessionModel.is_cancelled.is_(False))
    )
    session = db.execute(query).unique().scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Slides logic: hide URL unless unlocked OR session has ended
    now = datetime.now(timezone.utc)
    slides_url = None
    if session.slides_unlocked or now >= session.end_time:
        slides_url = session.slides_url

    # Build polls list for response
    polls_out = []
    for poll in session.polls:
        option_vote_counts = {}
        user_voted_option_id = None
        total_votes = 0
        for answer in poll.answers:
            option_vote_counts[answer.option_id] = option_vote_counts.get(answer.option_id, 0) + 1
            total_votes += 1
        options = [
            PollOptionOut(id=opt.id, text=opt.text, vote_count=option_vote_counts.get(opt.id, 0))
            for opt in poll.options
        ]
        polls_out.append(
            PollOut(
                id=poll.id,
                question=poll.question,
                session_id=poll.session_id,
                created_by=poll.created_by,
                is_active=poll.is_active,
                created_at=poll.created_at.isoformat(),
                options=options,
                user_voted_option_id=user_voted_option_id,
                total_votes=total_votes,
            )
        )

    return SessionDetailOut(
        id=session.id,
        title=session.title,
        description=session.description,
        start_time=session.start_time.isoformat(),
        end_time=session.end_time.isoformat(),
        type=session.type,
        topic_tags=session.topic_tags,
        image_url=session.image_url,
        venue=session.venue,
        speakers=[_user_to_speaker_brief(u) for u in session.speakers],
        is_cancelled=session.is_cancelled,
        cancelled_at=session.cancelled_at,
        slides_url=slides_url,
        slides_unlocked=session.slides_unlocked,
        polls=polls_out,
    )


@router.get("/sessions/{session_id}/polls", response_model=list[PollOut])
def get_session_polls(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
    active_only: bool = Query(False, description="Return only active polls"),
):
    """
    Get all polls for a session (active and inactive).
    Includes user_voted_option_id if authenticated, and vote counts per option.
    Use ?active_only=true to filter for active polls only.
    """
    # Verify session exists
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Get polls for this session
    query = select(Poll).where(Poll.session_id == session_id)
    if active_only:
        query = query.where(Poll.is_active == True)
    query = query.order_by(Poll.created_at.desc())
    polls = db.execute(query).scalars().all()

    current_user_id = current_user.id if current_user else None
    result = []

    for poll in polls:
        # Calculate vote counts per option
        option_vote_counts = {}
        user_voted_option_id = None
        total_votes = 0

        for answer in poll.answers:
            option_vote_counts[answer.option_id] = option_vote_counts.get(answer.option_id, 0) + 1
            total_votes += 1
            if current_user_id and answer.user_id == current_user_id:
                user_voted_option_id = answer.option_id

        options = [
            PollOptionOut(
                id=opt.id,
                text=opt.text,
                vote_count=option_vote_counts.get(opt.id, 0),
            )
            for opt in poll.options
        ]

        result.append(
            PollOut(
                id=poll.id,
                question=poll.question,
                session_id=poll.session_id,
                created_by=poll.created_by,
                is_active=poll.is_active,
                created_at=poll.created_at.isoformat(),
                options=options,
                user_voted_option_id=user_voted_option_id,
                total_votes=total_votes,
            )
        )

    return result


@router.get("/speakers", response_model=list[SpeakerOut])
def list_speakers(db: Session = Depends(get_db)):
    """List all users with role='speaker'."""
    query = (
        select(User)
        .where(User.role == UserRole.speaker)
        .order_by(User.full_name)
    )
    rows = db.execute(query).scalars().all()
    return [_user_to_speaker_full(u) for u in rows]


@router.get("/speakers/{speaker_id}", response_model=SpeakerWithSessionsOut)
def get_speaker_detail(
    speaker_id: int,
    db: Session = Depends(get_db),
):
    """Get speaker profile with their sessions. speaker_id is user_id."""
    # Find user by id with role check
    user = db.execute(
        select(User).where(User.id == speaker_id, User.role == UserRole.speaker)
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Ο ομιλητής δεν βρέθηκε.")

    # Get sessions for this speaker
    sessions_query = (
        select(SessionModel)
        .join(SessionModel.speakers)
        .options(joinedload(SessionModel.venue))
        .where(User.id == speaker_id)
    )
    sessions = db.execute(sessions_query).unique().scalars().all()

    # Convert sessions to brief format
    sessions_brief = [_session_to_brief(s) for s in sessions]

    speaker_data = _user_to_speaker_full(user)
    return SpeakerWithSessionsOut(
        **speaker_data,
        sessions=sessions_brief,
    )


# Removed /locations endpoint - use /venues from venues router instead


# -----------------------------
# AUTHENTICATED ENDPOINTS
# -----------------------------


@router.get("/my-agenda", response_model=list[AgendaItemOut])
def get_my_agenda(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's saved sessions, sorted by start_time."""
    query = (
        select(UserAgenda)
        .options(
            joinedload(UserAgenda.session)
            .joinedload(SessionModel.venue),
            joinedload(UserAgenda.session)
            .selectinload(SessionModel.speakers),
        )
        .where(UserAgenda.user_id == current_user.id)
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


@router.post("/sessions/{session_id}/favorite", response_model=FavoriteResponseOut)
def add_to_agenda(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a session to user's personal agenda.
    Returns a warning if there's a time conflict with existing saved sessions.
    """
    # Check session exists
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Check if already in agenda
    existing = db.execute(
        select(UserAgenda).where(
            UserAgenda.user_id == current_user.id,
            UserAgenda.session_id == session_id,
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Η συνεδρία υπάρχει ήδη στο πρόγραμμά σου.",
        )

    # Check for time conflicts with other saved sessions
    conflict_query = (
        select(SessionModel)
        .join(UserAgenda)
        .options(joinedload(SessionModel.venue))
        .where(
            UserAgenda.user_id == current_user.id,
            # Overlap: existing session starts before new ends AND existing ends after new starts
            SessionModel.start_time < session.end_time,
            SessionModel.end_time > session.start_time,
        )
    )
    conflicting_sessions = db.execute(conflict_query).unique().scalars().all()

    # Add to agenda
    agenda_item = UserAgenda(user_id=current_user.id, session_id=session_id)
    db.add(agenda_item)

    # Award points for attending/saving a session (ACT-01)
    award_points(db, current_user.id, "ATTEND_SESSION", 50, source_ref=str(session_id))

    db.commit()

    # Build response with conflict warning
    has_conflict = len(conflicting_sessions) > 0
    conflicts_brief = [_session_to_brief(s) for s in conflicting_sessions]

    message = "Η συνεδρία προστέθηκε στο πρόγραμμά σου."
    if has_conflict:
        message += " Προσοχή: υπάρχει χρονική επικάλυψη με άλλες αποθηκευμένες συνεδρίες."

    return FavoriteResponseOut(
        success=True,
        message=message,
        has_conflict=has_conflict,
        conflicting_sessions=conflicts_brief,
    )


@router.delete("/sessions/{session_id}/favorite")
def remove_from_agenda(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a session from user's personal agenda."""
    agenda_item = db.execute(
        select(UserAgenda).where(
            UserAgenda.user_id == current_user.id,
            UserAgenda.session_id == session_id,
        )
    ).scalar_one_or_none()

    if not agenda_item:
        raise HTTPException(
            status_code=404,
            detail="Η συνεδρία δεν βρέθηκε στο πρόγραμμά σου.",
        )

    db.delete(agenda_item)
    db.commit()

    return {"success": True, "message": "Η συνεδρία αφαιρέθηκε από το πρόγραμμά σου."}


# =====================================================================
#  EXHIBITOR / ADMIN SESSION MANAGEMENT
# =====================================================================

@router.post("/sessions", response_model=SessionOut)
def create_session(
    payload: SessionCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """
    Create a new session.

    Only admins + moderators with the `manage_sessions` scope reach this handler
    (Phase 12 D-13). Exhibitors/speakers creating sessions on their own behalf
    is out of scope for v2.0.
    """
    # Only admin/moderator reach here; created_by is the acting user.
    created_by_id = current_user.id

    # Parse datetime strings
    try:
        start_dt = datetime.fromisoformat(payload.start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(payload.end_time.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Μη έγκυρη μορφή ημερομηνίας. Χρησιμοποιήστε ISO format.",
        )
    
    # Validate times
    if end_dt <= start_dt:
        raise HTTPException(
            status_code=400,
            detail="Η ώρα λήξης πρέπει να είναι μετά την ώρα έναρξης.",
        )
    
    # Validate venue if provided
    if payload.venue_id:
        venue = db.execute(select(Venue).where(Venue.id == payload.venue_id)).scalar_one_or_none()
        if not venue:
            raise HTTPException(status_code=404, detail="Ο χώρος δεν βρέθηκε.")
    
    # Create the session
    new_session = SessionModel(
        title=payload.title,
        description=payload.description,
        start_time=start_dt,
        end_time=end_dt,
        type=payload.type,
        topic_tags=payload.topic_tags or [],
        image_url=payload.image_url,  # Support both field names
        venue_id=payload.venue_id,
        created_by=created_by_id,
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    # Add speakers from payload.speaker_ids (these are user_ids)
    if payload.speaker_ids:
        for user_id in payload.speaker_ids:
            # Verify user exists and has role='speaker'
            speaker_user = db.execute(
                select(User).where(User.id == user_id, User.role == UserRole.speaker)
            ).scalar_one_or_none()
            
            if speaker_user:
                new_session.speakers.append(speaker_user)
        
        db.commit()
    
    # Reload with relationships
    db.refresh(new_session)
    
    return _session_to_out(new_session)


@router.get("/exhibitors/{exhibitor_id}/sessions", response_model=list[SessionOut])
def get_exhibitor_sessions(
    exhibitor_id: int,
    db: Session = Depends(get_db),
):
    """
    Get all sessions created by an exhibitor.

    Returns sessions where created_by matches the exhibitor's user ID,
    sorted by start_time.
    """
    # Verify user exists and is an exhibitor
    user = db.execute(
        select(User).where(User.id == exhibitor_id, User.role == UserRole.exhibitor)
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Ο εκθέτης δεν βρέθηκε.")

    # Get sessions created by this exhibitor
    sessions_query = (
        select(SessionModel)
        .options(
            joinedload(SessionModel.venue),
            selectinload(SessionModel.speakers),
        )
        .where(SessionModel.created_by == exhibitor_id)
        .order_by(SessionModel.start_time)
    )
    sessions = db.execute(sessions_query).unique().scalars().all()

    return [_session_to_out(s) for s in sessions]


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """
    Hard-delete a session (rare — prefer soft-cancel via /admin/sessions/{id}/cancel).

    Only admins + moderators with `manage_sessions` scope can reach this handler
    (Phase 12 D-13).
    """
    # Get the session
    session = db.execute(
        select(SessionModel)
        .options(selectinload(SessionModel.speakers))
        .where(SessionModel.id == session_id)
    ).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Delete the session (CASCADE will handle user_agenda and session_speakers)
    db.delete(session)
    db.commit()

    return {"success": True, "message": "Η συνεδρία διαγράφηκε επιτυχώς."}


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """
    Update an existing session.

    Only admins + moderators with `manage_sessions` scope reach this handler
    (Phase 12 D-13). All fields are optional — only provided fields are
    updated. Setting `is_cancelled=false` uncancels; setting true via PATCH
    flips the flag without firing a push (see /admin/sessions/{id}/cancel
    for the canonical cancel+push flow).
    """
    session = db.execute(
        select(SessionModel)
        .options(
            joinedload(SessionModel.venue),
            selectinload(SessionModel.speakers),
        )
        .where(SessionModel.id == session_id)
    ).unique().scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Parse and validate times if provided
    start_dt = session.start_time
    end_dt = session.end_time

    if payload.start_time is not None:
        try:
            start_dt = datetime.fromisoformat(payload.start_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Μη έγκυρη μορφή start_time.")

    if payload.end_time is not None:
        try:
            end_dt = datetime.fromisoformat(payload.end_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Μη έγκυρη μορφή end_time.")

    if end_dt <= start_dt:
        raise HTTPException(
            status_code=400,
            detail="Η ώρα λήξης πρέπει να είναι μετά την ώρα έναρξης.",
        )

    # Apply scalar field updates
    if payload.title is not None:
        session.title = payload.title
    if payload.description is not None:
        session.description = payload.description
    if payload.type is not None:
        session.type = payload.type
    if payload.topic_tags is not None:
        session.topic_tags = payload.topic_tags
    if payload.image_url is not None:
        session.image_url = payload.image_url
    if payload.venue_id is not None:
        venue = db.execute(select(Venue).where(Venue.id == payload.venue_id)).scalar_one_or_none()
        if not venue:
            raise HTTPException(status_code=404, detail="Ο χώρος δεν βρέθηκε.")
        session.venue_id = payload.venue_id

    session.start_time = start_dt
    session.end_time = end_dt

    # Replace speakers if speaker_ids provided
    if payload.speaker_ids is not None:
        new_speakers = []
        for user_id in payload.speaker_ids:
            speaker_user = db.execute(
                select(User).where(User.id == user_id, User.role == UserRole.speaker)
            ).scalar_one_or_none()
            if speaker_user:
                new_speakers.append(speaker_user)
        session.speakers = new_speakers

    # Soft-cancel flip via PATCH (Phase 12 D-04).
    # Note: setting is_cancelled=True via PATCH is allowed but does NOT fan out a push.
    # The Plan 02 /admin/sessions/{id}/cancel endpoint is the canonical path that fires push.
    if payload.is_cancelled is not None:
        session.is_cancelled = payload.is_cancelled
        if payload.is_cancelled is False:
            session.cancelled_at = None

    db.commit()
    db.refresh(session)

    return _session_to_out(session)
