"""
Scheduling & Meetings API routes.

Endpoints:
- GET /scheduling/availability/{user_id}      - Get time slot availability for meeting with user
- GET /scheduling/conflicts                   - Get conflict details and alternatives
- GET /scheduling/locations                   - Get available meeting locations
- POST /scheduling/meetings                   - Create meeting request
- PATCH /scheduling/meetings/{id}             - Accept/decline/cancel meeting
- PUT /scheduling/meetings/{id}/reschedule    - Reschedule meeting to new time
- GET /scheduling/meetings                    - Get user's meetings
"""

from datetime import datetime, timezone, timedelta, date, time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import MeetingStatus
from app.services.push import send_push
from app.services.google_calendar import get_google_busy_times
from app.models.user import User
from app.models.session import Session as SessionModel
from app.models.user_agenda import UserAgenda
from app.models.meeting import Meeting
from app.models.map_feature import MapFeature
from app.services.config_reader import get_config_value
from app.api.schemas import (
    AvailabilityOut,
    DayScheduleOut,
    TimeSlotOut,
    ScheduleUserOut,
    ScheduleOverlapOut,
    MeetingLocationOut,
    CreateMeetingIn,
    MeetingActionIn,
    RescheduleMeetingIn,
    MeetingOut,
    MeetingsListOut,
    ConnectionUserOut,
    ConnectionsOut,
)

router = APIRouter(dependencies=[require_feature("scheduling")])

# -----------------------------
# FESTIVAL CONFIGURATION (defaults)
# -----------------------------

FESTIVAL_START = date(2026, 5, 20)   # Wednesday (matches session seed data)
FESTIVAL_END = date(2026, 5, 24)     # Sunday

MEETING_SLOT_START = time(9, 0)   # 9:00 AM
MEETING_SLOT_END = time(18, 0)    # 6:00 PM
SLOT_DURATION_MINUTES = 30

MEETING_HOLD_MINUTES = 120

DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

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


# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def _get_schedule_config(db: Session) -> dict:
    """Load schedule config from AppConfig, falling back to defaults."""
    return get_config_value(db, "schedule_config", DEFAULT_SCHEDULE_CONFIG)


def _generate_time_slots(slot_start: time, slot_end: time, slot_duration: int) -> List[dict]:
    """Generate all available time slots for a day."""
    slots = []
    current = datetime.combine(date.today(), slot_start)
    end = datetime.combine(date.today(), slot_end)

    while current < end:
        period = "AM" if current.hour < 12 else "PM"
        slots.append({
            "time": current.strftime("%H:%M"),
            "period": period,
        })
        current += timedelta(minutes=slot_duration)

    return slots


def _get_festival_days(festival_start: date, festival_end: date) -> List[date]:
    """Get list of festival dates."""
    days = []
    current = festival_start
    while current <= festival_end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _parse_schedule_config(cfg: dict) -> tuple:
    """Parse config dict into (festival_start, festival_end, slot_start, slot_end, slot_duration, hold_minutes)."""
    festival_start = date.fromisoformat(cfg.get("festival_start", "2026-05-20"))
    festival_end = date.fromisoformat(cfg.get("festival_end", "2026-05-24"))
    slot_start = time(cfg.get("slot_start_hour", 9), cfg.get("slot_start_minute", 0))
    slot_end = time(cfg.get("slot_end_hour", 18), cfg.get("slot_end_minute", 0))
    slot_duration = cfg.get("slot_duration_minutes", 30)
    hold_minutes = cfg.get("meeting_hold_minutes", 120)
    return festival_start, festival_end, slot_start, slot_end, slot_duration, hold_minutes


def _user_to_schedule_user(user: User) -> ScheduleUserOut:
    """Convert User model to ScheduleUserOut."""
    # Determine badge from role
    badge = user.role.value.capitalize() if user.role else "Attendee"

    # Build title from company
    title = user.company if user.company else None

    return ScheduleUserOut(
        id=user.id,
        name=user.full_name or "Unknown",
        title=title,
        company=user.company,
        badge=badge,
        avatar_url=user.avatar_url,
    )


def _get_user_busy_times(
    db: Session,
    user_id: int,
    day: date,
    include_gcal: bool = False,
) -> tuple[List[tuple[datetime, datetime]], List[tuple[datetime, datetime]]]:
    """
    Get all busy time ranges for a user on a specific day.
    Returns (festival_busy, gcal_busy) tuple.
    Festival busy combines: agenda sessions + confirmed/pending meetings.
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

    # 3. Google Calendar busy times (optional)
    gcal_busy = []
    if include_gcal:
        gcal_result = get_google_busy_times(db, user_id, day_start, day_end)
        if gcal_result:
            gcal_busy = gcal_result

    return busy_times, gcal_busy


def _is_time_slot_busy(
    slot_start: datetime,
    slot_end: datetime,
    busy_times: List[tuple[datetime, datetime]]
) -> bool:
    """Check if a time slot overlaps with any busy times."""
    for busy_start, busy_end in busy_times:
        # Overlap: slot starts before busy ends AND slot ends after busy starts
        if slot_start < busy_end and slot_end > busy_start:
            return True
    return False


def _get_conflict_session(
    db: Session,
    user_id: int,
    slot_start: datetime,
    slot_end: datetime
) -> Optional[SessionModel]:
    """Get the session causing a conflict at a specific time."""
    day_start = datetime.combine(slot_start.date(), time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(slot_start.date(), time.max, tzinfo=timezone.utc)

    query = (
        select(SessionModel)
        .join(UserAgenda)
        .where(
            UserAgenda.user_id == user_id,
            SessionModel.start_time >= day_start,
            SessionModel.start_time <= day_end,
            SessionModel.start_time < slot_end,
            SessionModel.end_time > slot_start,
        )
    )
    return db.execute(query).scalar_one_or_none()


def _meeting_to_out(meeting: Meeting, db: Session) -> MeetingOut:
    """Convert Meeting model to MeetingOut schema."""
    # Get location info if set
    location = None
    if meeting.map_feature_id and meeting.map_feature:
        location = MeetingLocationOut(
            id=meeting.map_feature.id,
            name=meeting.map_feature.name,
            venue_name=meeting.map_feature.venue.name if hasattr(meeting.map_feature, 'venue') and meeting.map_feature.venue else None,
        )

    return MeetingOut(
        id=meeting.id,
        requester=_user_to_schedule_user(meeting.requester),
        recipient=_user_to_schedule_user(meeting.recipient),
        proposed_start=meeting.proposed_start.isoformat(),
        proposed_end=meeting.proposed_end.isoformat(),
        status=meeting.status.value,
        location=location,
        message=meeting.message,
        expires_at=meeting.expires_at.isoformat() if meeting.expires_at else None,
        created_at=meeting.created_at.isoformat(),
    )


# -----------------------------
# PUBLIC ENDPOINTS
# -----------------------------


@router.get("/scheduling/availability/{user_id}", response_model=AvailabilityOut)
def get_availability(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get time slot availability for scheduling a meeting with target user.

    Returns all festival days with time slots marked as:
    - mutual_free: both users are free
    - them_only: target is free, current user has a conflict
    - conflict: target is busy
    """
    # Get target user
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Can't schedule with yourself
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot schedule meeting with yourself")

    cfg = _get_schedule_config(db)
    fs, fe, ss, se, sd, _ = _parse_schedule_config(cfg)
    festival_days = _get_festival_days(fs, fe)
    base_slots = _generate_time_slots(ss, se, sd)

    # Pre-fetch Google Calendar busy times for the ENTIRE festival range (1 API call per user)
    festival_start_dt = datetime.combine(festival_days[0], time.min, tzinfo=timezone.utc)
    festival_end_dt = datetime.combine(festival_days[-1], time.max, tzinfo=timezone.utc)
    my_gcal_all = get_google_busy_times(db, current_user.id, festival_start_dt, festival_end_dt) or []
    their_gcal_all = get_google_busy_times(db, user_id, festival_start_dt, festival_end_dt) or []

    days_out = []

    for day in festival_days:
        # Get festival busy times (DB queries — fast)
        my_festival_busy, _ = _get_user_busy_times(db, current_user.id, day, include_gcal=False)
        their_festival_busy, _ = _get_user_busy_times(db, user_id, day, include_gcal=False)

        # Filter pre-fetched gcal busy times to this day
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        my_gcal_busy = [(s, e) for s, e in my_gcal_all if s < day_end and e > day_start]
        their_gcal_busy = [(s, e) for s, e in their_gcal_all if s < day_end and e > day_start]

        their_busy = their_festival_busy + their_gcal_busy

        slots_out = []
        for slot_info in base_slots:
            # Create datetime for this slot
            slot_time = datetime.strptime(slot_info["time"], "%H:%M").time()
            slot_start = datetime.combine(day, slot_time, tzinfo=timezone.utc)
            slot_end = slot_start + timedelta(minutes=sd)

            # Determine slot status
            their_busy_now = _is_time_slot_busy(slot_start, slot_end, their_busy)
            my_festival_busy_now = _is_time_slot_busy(slot_start, slot_end, my_festival_busy)
            my_gcal_busy_now = _is_time_slot_busy(slot_start, slot_end, my_gcal_busy)

            if their_busy_now:
                status = "conflict"
            elif my_gcal_busy_now:
                status = "gcal_busy"
            elif my_festival_busy_now:
                status = "them_only"
            else:
                status = "mutual_free"

            slots_out.append(TimeSlotOut(
                time=slot_info["time"],
                period=slot_info["period"],
                status=status,
            ))

        days_out.append(DayScheduleOut(
            day_short=DAY_NAMES[day.weekday()],
            date=day.day,
            full_date=day.isoformat(),
            slots=slots_out,
        ))

    return AvailabilityOut(
        target_user=_user_to_schedule_user(target_user),
        festival_days=days_out,
    )


@router.get("/scheduling/conflicts", response_model=ScheduleOverlapOut)
def get_conflicts(
    user_id: int = Query(..., description="Target user ID"),
    date_str: str = Query(..., alias="date", description="Date (YYYY-MM-DD)"),
    time_str: str = Query(..., alias="time", description="Time (HH:MM)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get conflict details when selecting a conflicting time slot.
    Returns the event causing the conflict and alternative free times.
    """
    # Parse date and time
    try:
        selected_date = date.fromisoformat(date_str)
        selected_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    cfg = _get_schedule_config(db)
    _, _, ss, se, sd, _ = _parse_schedule_config(cfg)

    slot_start = datetime.combine(selected_date, selected_time, tzinfo=timezone.utc)
    slot_end = slot_start + timedelta(minutes=sd)

    # Get target user
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find what's causing the conflict for current user
    my_conflict_session = _get_conflict_session(db, current_user.id, slot_start, slot_end)

    event_name = "Unknown event"
    event_time = time_str
    if my_conflict_session:
        event_name = my_conflict_session.title
        event_time = my_conflict_session.start_time.strftime("%I:%M %p").lstrip("0")

    # Find alternative times when both are free
    my_busy, _ = _get_user_busy_times(db, current_user.id, selected_date)
    their_busy, _ = _get_user_busy_times(db, user_id, selected_date)

    alternatives = []
    base_slots = _generate_time_slots(ss, se, sd)

    for slot_info in base_slots:
        slot_time = datetime.strptime(slot_info["time"], "%H:%M").time()
        alt_start = datetime.combine(selected_date, slot_time, tzinfo=timezone.utc)
        alt_end = alt_start + timedelta(minutes=sd)

        # Only suggest if both are free
        if not _is_time_slot_busy(alt_start, alt_end, my_busy) and \
           not _is_time_slot_busy(alt_start, alt_end, their_busy):
            # Format as "02:00 PM"
            formatted = alt_start.strftime("%I:%M %p").lstrip("0")
            alternatives.append(formatted)

    # Limit to 4 alternatives
    alternatives = alternatives[:4]

    return ScheduleOverlapOut(
        event_name=event_name,
        time=event_time,
        person_name=target_user.full_name or "User",
        alternative_times=alternatives,
    )


@router.get("/scheduling/locations", response_model=List[MeetingLocationOut])
def get_available_locations(
    date_str: str = Query(..., alias="date", description="Date (YYYY-MM-DD)"),
    time_str: str = Query(..., alias="time", description="Time (HH:MM)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get available meeting locations for a specific date/time.
    Returns rooms not already booked for that slot.
    """
    # Parse date and time
    try:
        selected_date = date.fromisoformat(date_str)
        selected_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    cfg = _get_schedule_config(db)
    _, _, _, _, sd_loc, _ = _parse_schedule_config(cfg)

    slot_start = datetime.combine(selected_date, selected_time, tzinfo=timezone.utc)
    slot_end = slot_start + timedelta(minutes=sd_loc)

    # Get all rooms (feature_type = 'room'), sorted by name
    rooms_query = (
        select(MapFeature)
        .options(joinedload(MapFeature.venue))
        .where(MapFeature.feature_type == "room")
        .order_by(MapFeature.name)
    )
    all_rooms = db.execute(rooms_query).unique().scalars().all()

    # Get rooms already booked for this slot
    booked_query = (
        select(Meeting.map_feature_id)
        .where(
            Meeting.map_feature_id.isnot(None),
            Meeting.status.in_([MeetingStatus.pending, MeetingStatus.confirmed]),
            Meeting.proposed_start < slot_end,
            Meeting.proposed_end > slot_start,
        )
    )
    booked_ids = set(db.execute(booked_query).scalars().all())

    # Filter to available rooms
    available = []
    for room in all_rooms:
        if room.id not in booked_ids:
            venue_name = None
            if hasattr(room, 'venue') and room.venue:
                venue_name = room.venue.name
            available.append(MeetingLocationOut(
                id=room.id,
                name=room.name or room.feature_key,
                venue_name=venue_name,
            ))

    return available


@router.post("/scheduling/meetings", response_model=MeetingOut)
def create_meeting(
    data: CreateMeetingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new meeting request.
    Sets a 120-minute expiration for the recipient to respond.
    """
    # Validate recipient exists
    recipient = db.get(User, data.recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    if data.recipient_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create meeting with yourself")

    # Parse times
    try:
        proposed_start = datetime.fromisoformat(data.proposed_start)
        proposed_end = datetime.fromisoformat(data.proposed_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Ensure timezone awareness
    if proposed_start.tzinfo is None:
        proposed_start = proposed_start.replace(tzinfo=timezone.utc)
    if proposed_end.tzinfo is None:
        proposed_end = proposed_end.replace(tzinfo=timezone.utc)

    # Check for existing pending/confirmed meeting between these users at this time
    existing = db.execute(
        select(Meeting).where(
            or_(
                and_(
                    Meeting.requester_id == current_user.id,
                    Meeting.recipient_id == data.recipient_id,
                ),
                and_(
                    Meeting.requester_id == data.recipient_id,
                    Meeting.recipient_id == current_user.id,
                ),
            ),
            Meeting.status.in_([MeetingStatus.pending, MeetingStatus.confirmed]),
            Meeting.proposed_start < proposed_end,
            Meeting.proposed_end > proposed_start,
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="A meeting request already exists with this user for this time slot"
        )

    # Validate location if provided
    location = None
    if data.location_id:
        location = db.get(MapFeature, data.location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

    # Create meeting with expiration
    cfg = _get_schedule_config(db)
    _, _, _, _, _, hold_min = _parse_schedule_config(cfg)

    now = datetime.now(timezone.utc)
    meeting = Meeting(
        requester_id=current_user.id,
        recipient_id=data.recipient_id,
        proposed_start=proposed_start,
        proposed_end=proposed_end,
        status=MeetingStatus.pending,
        expires_at=now + timedelta(minutes=hold_min),
        map_feature_id=data.location_id,
        message=data.message,
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Reload with relationships
    meeting = db.execute(
        select(Meeting)
        .options(
            joinedload(Meeting.requester),
            joinedload(Meeting.recipient),
            joinedload(Meeting.map_feature),
        )
        .where(Meeting.id == meeting.id)
    ).unique().scalar_one()

    # Notify the recipient
    requester_name = current_user.full_name or "Someone"
    time_label = proposed_start.strftime("%b %d at %H:%M")
    send_push(
        db=db,
        user_id=data.recipient_id,
        title="Meeting Request",
        body=f"{requester_name} wants to meet on {time_label}",
        notif_type="meeting",
        ref_id=meeting.id,
        deeplink="/(tabs)/(schedule)/my-meetings",
    )
    db.commit()

    return _meeting_to_out(meeting, db)


@router.patch("/scheduling/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: int,
    data: MeetingActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accept, decline, or cancel a meeting request.

    - accept: Only recipient can accept (status -> confirmed)
    - decline: Only recipient can decline (status -> declined)
    - cancel: Either party can cancel (status -> cancelled)
    """
    meeting = db.execute(
        select(Meeting)
        .options(
            joinedload(Meeting.requester),
            joinedload(Meeting.recipient),
            joinedload(Meeting.map_feature),
        )
        .where(Meeting.id == meeting_id)
    ).unique().scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check user is part of this meeting
    is_requester = meeting.requester_id == current_user.id
    is_recipient = meeting.recipient_id == current_user.id

    if not is_requester and not is_recipient:
        raise HTTPException(status_code=403, detail="Not authorized for this meeting")

    action = data.action.lower()

    if action == "accept":
        if not is_recipient:
            raise HTTPException(status_code=403, detail="Only recipient can accept")
        if meeting.status != MeetingStatus.pending:
            raise HTTPException(status_code=400, detail="Meeting is not pending")

        meeting.status = MeetingStatus.confirmed
        meeting.expires_at = None  # Clear expiration

        # Notify the requester that their meeting was accepted
        recipient_name = current_user.full_name or "Someone"
        time_label = meeting.proposed_start.strftime("%b %d at %H:%M")
        send_push(
            db=db,
            user_id=meeting.requester_id,
            title="Meeting Accepted",
            body=f"{recipient_name} accepted your meeting on {time_label}",
            notif_type="meeting",
            ref_id=meeting.id,
            deeplink="/(tabs)/(schedule)/my-meetings",
        )

    elif action == "decline":
        if not is_recipient:
            raise HTTPException(status_code=403, detail="Only recipient can decline")
        if meeting.status != MeetingStatus.pending:
            raise HTTPException(status_code=400, detail="Meeting is not pending")

        meeting.status = MeetingStatus.declined
        meeting.expires_at = None

    elif action == "cancel":
        if meeting.status not in [MeetingStatus.pending, MeetingStatus.confirmed]:
            raise HTTPException(status_code=400, detail="Meeting cannot be cancelled")

        meeting.status = MeetingStatus.cancelled
        meeting.expires_at = None

    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use: accept, decline, cancel")

    meeting.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(meeting)

    return _meeting_to_out(meeting, db)


@router.put("/scheduling/meetings/{meeting_id}/reschedule", response_model=MeetingOut)
def reschedule_meeting(
    meeting_id: int,
    data: RescheduleMeetingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reschedule an existing meeting to a new time.

    - Either party (requester or recipient) can reschedule
    - Only pending or confirmed meetings can be rescheduled
    - Status resets to pending, requiring the other party to accept
    - The user who reschedules becomes the new requester
    - Expiration timer resets to 120 minutes
    """
    meeting = db.execute(
        select(Meeting)
        .options(
            joinedload(Meeting.requester),
            joinedload(Meeting.recipient),
            joinedload(Meeting.map_feature),
        )
        .where(Meeting.id == meeting_id)
    ).unique().scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check user is part of this meeting
    is_requester = meeting.requester_id == current_user.id
    is_recipient = meeting.recipient_id == current_user.id

    if not is_requester and not is_recipient:
        raise HTTPException(status_code=403, detail="Not authorized for this meeting")

    # Only pending or confirmed meetings can be rescheduled
    if meeting.status not in [MeetingStatus.pending, MeetingStatus.confirmed]:
        raise HTTPException(
            status_code=400,
            detail="Only pending or confirmed meetings can be rescheduled"
        )

    # Parse new times
    try:
        proposed_start = datetime.fromisoformat(data.proposed_start)
        proposed_end = datetime.fromisoformat(data.proposed_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    # Ensure timezone awareness
    if proposed_start.tzinfo is None:
        proposed_start = proposed_start.replace(tzinfo=timezone.utc)
    if proposed_end.tzinfo is None:
        proposed_end = proposed_end.replace(tzinfo=timezone.utc)

    # Validate time range
    if proposed_end <= proposed_start:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    # Validate location if provided
    if data.location_id:
        location = db.get(MapFeature, data.location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

    # Determine the other party (they need to accept the new time)
    other_user_id = meeting.recipient_id if is_requester else meeting.requester_id

    cfg = _get_schedule_config(db)
    _, _, _, _, _, hold_min = _parse_schedule_config(cfg)

    now = datetime.now(timezone.utc)

    # Update meeting: swap requester/recipient so current user is requester
    # This means the other party needs to accept the rescheduled time
    meeting.requester_id = current_user.id
    meeting.recipient_id = other_user_id
    meeting.proposed_start = proposed_start
    meeting.proposed_end = proposed_end
    meeting.status = MeetingStatus.pending
    meeting.expires_at = now + timedelta(minutes=hold_min)
    meeting.updated_at = now

    if data.location_id is not None:
        meeting.map_feature_id = data.location_id

    if data.message is not None:
        meeting.message = data.message

    db.commit()
    db.refresh(meeting)

    return _meeting_to_out(meeting, db)


@router.get("/scheduling/meetings", response_model=MeetingsListOut)
def get_my_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current user's meetings categorized as:
    - incoming: Requests received (pending)
    - outgoing: Requests sent (pending)
    - confirmed: Confirmed meetings
    """
    # Base query with relationships
    base_query = (
        select(Meeting)
        .options(
            joinedload(Meeting.requester),
            joinedload(Meeting.recipient),
            joinedload(Meeting.map_feature),
        )
    )

    # Incoming requests (user is recipient, status is pending)
    incoming_query = base_query.where(
        Meeting.recipient_id == current_user.id,
        Meeting.status == MeetingStatus.pending,
    ).order_by(Meeting.proposed_start)
    incoming = db.execute(incoming_query).unique().scalars().all()

    # Outgoing requests (user is requester, status is pending)
    outgoing_query = base_query.where(
        Meeting.requester_id == current_user.id,
        Meeting.status == MeetingStatus.pending,
    ).order_by(Meeting.proposed_start)
    outgoing = db.execute(outgoing_query).unique().scalars().all()

    # Confirmed meetings (user is either party, status is confirmed)
    confirmed_query = base_query.where(
        or_(
            Meeting.requester_id == current_user.id,
            Meeting.recipient_id == current_user.id,
        ),
        Meeting.status == MeetingStatus.confirmed,
    ).order_by(Meeting.proposed_start)
    confirmed = db.execute(confirmed_query).unique().scalars().all()

    return MeetingsListOut(
        incoming=[_meeting_to_out(m, db) for m in incoming],
        outgoing=[_meeting_to_out(m, db) for m in outgoing],
        confirmed=[_meeting_to_out(m, db) for m in confirmed],
    )


@router.get("/scheduling/connections", response_model=ConnectionsOut)
def get_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns users the current user has a confirmed meeting with.
    """
    meetings = db.execute(
        select(Meeting)
        .options(joinedload(Meeting.requester), joinedload(Meeting.recipient))
        .where(
            or_(
                Meeting.requester_id == current_user.id,
                Meeting.recipient_id == current_user.id,
            ),
            Meeting.status == MeetingStatus.confirmed,
        )
    ).unique().scalars().all()

    seen: set[int] = set()
    users: list[ConnectionUserOut] = []
    for m in meetings:
        other = m.recipient if m.requester_id == current_user.id else m.requester
        if other.id not in seen:
            seen.add(other.id)
            users.append(ConnectionUserOut(user_id=other.id, user_name=other.full_name, avatar=other.avatar_url))

    return ConnectionsOut(total=len(users), users=users)


# -----------------------------
# BACKGROUND JOB HELPER
# -----------------------------
# This function can be called by a cron job or scheduler

def expire_pending_meetings(db: Session) -> int:
    """
    Mark expired pending meetings as expired.
    Returns count of expired meetings.

    Call this from a background job/cron:
    ```
    from app.db.session import SessionLocal
    from app.api.routes.scheduling import expire_pending_meetings

    db = SessionLocal()
    try:
        count = expire_pending_meetings(db)
        print(f"Expired {count} meetings")
    finally:
        db.close()
    ```
    """
    now = datetime.now(timezone.utc)

    expired_meetings = db.execute(
        select(Meeting).where(
            Meeting.status == MeetingStatus.pending,
            Meeting.expires_at.isnot(None),
            Meeting.expires_at < now,
        )
    ).scalars().all()

    for meeting in expired_meetings:
        meeting.status = MeetingStatus.expired
        meeting.updated_at = now

    db.commit()

    return len(expired_meetings)
