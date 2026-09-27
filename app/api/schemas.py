# backend/app/api/schemas.py
# ------------------------------------------------------------
# ΕΝΑ ΚΑΙ ΜΟΝΑΔΙΚΟ ΣΗΜΕΙΟ για όλα τα Pydantic schemas που κάνουν import τα routes.
# Στόχος: να ΣΤΑΜΑΤΗΣΟΥΝ τα ImportError και να σηκωθεί ξανά το /docs.
# ------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, EmailStr, Field
from app.core.enums import UserRole, OnboardingStatus, ExperienceLevel, DiscussionTopic, GroupMemberRole, GroupMessageType


# -----------------------------
# AUTH / USERS
# -----------------------------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=2)
    # role προαιρετικό στο register (αν δεν σταλεί -> attendee)
    role: Optional[UserRole] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class EventoraMagicLinkIn(BaseModel):
    token: str = Field(min_length=20, max_length=8192)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    linkedin_url: Optional[str] = None
    points: int = 0
    theme_preference: Optional[str] = None
    last_seen: Optional[str] = None  # ISO string
    created_at: str  # ISO string
    date_of_birth: Optional[str] = None  # ISO date string "YYYY-MM-DD"
    gender: Optional[str] = None
    # Phase 11: present only when role == moderator; null otherwise.
    moderator_permissions: Optional[Dict[str, bool]] = None
    eventora_qr_code: Optional[str] = None

    class Config:
        from_attributes = True


# -----------------------------
# FESTY FIRST PHASE
# -----------------------------

class FirstPhaseRegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str


class FirstPhaseUserOut(BaseModel):
    id: str
    email: EmailStr
    name: str

    class Config:
        from_attributes = True


class FirstPhaseLoginOut(BaseModel):
    token: str
    user: FirstPhaseUserOut


class ModeratorPermissionsIn(BaseModel):
    """Admin-only write payload for PUT /admin/moderator-permissions."""
    validate_ticket: bool = False
    ticket_packages: bool = False
    user_reports: bool = False


class ModeratorPermissionsOut(BaseModel):
    """Response shape for GET/PUT /admin/moderator-permissions."""
    validate_ticket: bool
    ticket_packages: bool
    user_reports: bool


class UserUpdateIn(BaseModel):
    """Schema for updating user profile fields."""
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    linkedin_url: Optional[str] = None
    date_of_birth: Optional[str] = None  # ISO date string "YYYY-MM-DD"
    gender: Optional[str] = None


class UserProfileOut(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    full_name: str
    role: str  # "attendee", "exhibitor", "speaker", "admin"
    company: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    interests: Optional[list[str]] = None
    sessions: Optional[list[SessionBriefOut]] = None

    class Config:
        from_attributes = True


class UserListItemOut(BaseModel):
    """User item for list endpoint."""
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    company: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    interests: List[str] = []

    class Config:
        from_attributes = True


class UsersListOut(BaseModel):
    """Paginated users list response."""
    users: List[UserListItemOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# -----------------------------
# GROUPS
# (για να μην σκάει: from app.api.schemas import GroupOut, JoinGroupIn, ...
# Αν έχεις παραπάνω πεδία στα μοντέλα σου, μπορείς να τα προσθέσεις μετά.
# -----------------------------

class JoinGroupIn(BaseModel):
    group_id: Optional[int] = None
    ref_key: Optional[str] = None


class GroupOut(BaseModel):
    id: int
    group_type: str
    ref_key: str
    title: str
    description: Optional[str] = None
    member_count: int = 0
    match_percentage: Optional[float] = None  # Percentage based on common interests

    class Config:
        from_attributes = True


class GroupsListOut(BaseModel):
    """Paginated groups list response."""
    groups: List[GroupOut]
    total: int
    limit: int
    offset: int


# -----------------------------
# VENUES / FLOORS / GEOJSON
# (για να μην σκάει: VenueOut, VenueFloorOut, GeoJsonOut)
# -----------------------------

class GeoJsonOut(BaseModel):
    """Response for floor GeoJSON endpoint."""
    venue_id: int
    floor_number: int
    geojson: Dict[str, Any]  # The actual GeoJSON FeatureCollection

    class Config:
        from_attributes = True


class VenueFloorOut(BaseModel):
    id: int
    venue_id: int
    floor_number: int

    class Config:
        from_attributes = True


class VenueOut(BaseModel):
    id: int
    key: str
    name: str
    lat: float
    lng: float
    default_zoom: float = 16.0
    has_indoor: bool = True

    class Config:
        from_attributes = True


# -----------------------------
# DM / MESSAGES / REPORTS
# (για να μην σκάει: SendMessageIn, ConversationOut, MessageOut, ReportUserIn)
# -----------------------------

class SendMessageIn(BaseModel):
    to_user_id: int
    text: str


class MessageOut(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    text: str
    created_at: Optional[str] = None  # κρατάμε string για να μη σκάει σε serialization


class ConversationUserOut(BaseModel):
    id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None


class ConversationOut(BaseModel):
    id: int
    other_user: ConversationUserOut
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None


class ReportUserIn(BaseModel):
    reason: Literal["inappropriate", "spam", "harassment", "offensive", "other"]
    details: str | None = None


class ConnectionUserOut(BaseModel):
    user_id: int
    user_name: Optional[str] = None
    avatar: Optional[str] = None


class ConnectionsOut(BaseModel):
    total: int
    users: List[ConnectionUserOut]


# -----------------------------
# INTERESTS
# -----------------------------

class InterestOut(BaseModel):
    id: int
    name: str


class SetInterestsIn(BaseModel):
    interest_ids: List[int] = Field(default_factory=list)


# -----------------------------
# MATCHING
# -----------------------------

class MatchedUserOut(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    # User profile fields (same as UserProfileOut)
    role: str  # "attendee", "exhibitor", "speaker", "admin"
    company: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    interests: Optional[List[str]] = None
    sessions: Optional[List[SessionBriefOut]] = None
    # Matching-specific fields
    common_interests: List[str]
    common_goals: List[str]
    common_groups: List[str]
    common_discussion_topics: List[str]
    same_level: bool
    match_score: float  # New scoring system (can exceed 100)


# -----------------------------
# PROGRAM & SESSIONS
# -----------------------------

class SessionVenueOut(BaseModel):
    """Venue info for session responses."""
    id: int
    name: str
    key: str

    class Config:
        from_attributes = True


class SpeakerBriefOut(BaseModel):
    """Compact speaker info for session listings."""
    user_id: int
    full_name: str
    company: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class SpeakerOut(BaseModel):
    """Full speaker profile - data comes from User."""
    user_id: int
    full_name: str
    email: EmailStr
    company: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    linkedin_url: str | None = None

    class Config:
        from_attributes = True


class SessionBriefOut(BaseModel):
    """Compact session info for speaker profiles."""
    id: int
    title: str
    start_time: str  # ISO string
    end_time: str  # ISO string
    type: str
    venue_name: str | None = None

    class Config:
        from_attributes = True


class SpeakerWithSessionsOut(SpeakerOut):
    """Speaker profile with their sessions."""
    sessions: list[SessionBriefOut] = []


class SessionOut(BaseModel):
    """Session listing with speakers and venue."""
    id: int
    title: str
    description: str | None = None
    start_time: str  # ISO string
    end_time: str  # ISO string
    type: str
    topic_tags: list[str] | None = None
    image_url: str | None = None
    venue: SessionVenueOut | None = None
    speakers: list[SpeakerBriefOut] = []
    is_cancelled: bool = False
    cancelled_at: datetime | None = None

    class Config:
        from_attributes = True


class SessionDetailOut(SessionOut):
    """Detailed session view with slides (if unlocked)."""
    slides_url: str | None = None
    slides_unlocked: bool = False
    polls: List[PollOut] = []


class SessionImpactOut(BaseModel):
    """Impact counts for the admin cancel-confirmation modal (Phase 12 D-05)."""
    favorites: int
    chat_messages: int
    qa_items: int


class AdminSessionListItemOut(SessionOut):
    """Admin list entry — identical to SessionOut but with explicit status note.

    Phase 12 D-09: admin list returns all rows (including cancelled when
    show_cancelled=true). Kept as a distinct type so Plan 03 mobile can bind
    against it without relying on the public SessionOut default.
    """
    # No new fields beyond SessionOut.
    pass


class NotifyUpdateIn(BaseModel):
    """Body for POST /admin/sessions/{id}/notify-update (Phase 12 D-22)."""
    changed_fields: list[str]  # subset of {"time", "venue"}; server validates


class SessionCreateIn(BaseModel):
    """Schema for creating a new session (exhibitor/admin/speaker)."""
    title: str
    description: str | None = None
    start_time: str  # ISO string
    end_time: str  # ISO string
    type: str = "workshop"
    topic_tags: list[str] | None = None
    image_url: str | None = None
    venue_id: int | None = None
    speaker_ids: list[int] | None = None
    exhibitor_id: int | None = None  # Required when a speaker creates a session


class SessionUpdateIn(BaseModel):
    """Schema for updating an existing session (exhibitor/admin only). All fields optional."""
    title: str | None = None
    description: str | None = None
    start_time: str | None = None  # ISO string
    end_time: str | None = None  # ISO string
    type: str | None = None
    topic_tags: list[str] | None = None
    image_url: str | None = None
    venue_id: int | None = None
    speaker_ids: list[int] | None = None
    is_cancelled: bool | None = None


class AgendaItemOut(BaseModel):
    """User's saved session with metadata."""
    id: int
    session: SessionOut
    created_at: str  # ISO string - when user added to agenda

    class Config:
        from_attributes = True


class FavoriteResponseOut(BaseModel):
    """Response when adding a session to agenda."""
    success: bool
    message: str
    has_conflict: bool = False
    conflicting_sessions: list[SessionBriefOut] = []


# -----------------------------
# SCHEDULING & MEETINGS
# -----------------------------

class TimeSlotStatus(str):
    """Status of a time slot for meeting scheduling."""
    MUTUAL_FREE = "mutual_free"  # Both users are free
    THEM_ONLY = "them_only"      # Target is free, current user has conflict
    CONFLICT = "conflict"        # Target is busy
    GCAL_BUSY = "gcal_busy"      # Current user has Google Calendar conflict


class TimeSlotOut(BaseModel):
    """A single time slot with availability status."""
    time: str           # e.g., "09:00"
    period: str         # "AM" or "PM"
    status: str         # mutual_free, them_only, conflict


class DayScheduleOut(BaseModel):
    """A festival day with time slots."""
    day_short: str      # e.g., "MON", "TUE"
    date: int           # Day of month (14, 15, etc.)
    full_date: str      # ISO date string for API calls
    slots: List[TimeSlotOut]


class ScheduleUserOut(BaseModel):
    """Target user info for scheduling screen."""
    id: int
    name: str
    title: Optional[str] = None   # e.g., "CTO, NexaSystems"
    company: Optional[str] = None
    badge: Optional[str] = None   # e.g., "Speaker", "Attendee"
    avatar_url: Optional[str] = None


class AvailabilityOut(BaseModel):
    """Full availability response for scheduling screen."""
    target_user: ScheduleUserOut
    festival_days: List[DayScheduleOut]


class ScheduleOverlapOut(BaseModel):
    """Conflict details with alternative suggestions."""
    event_name: str              # e.g., "Web3 Keynote"
    time: str                    # e.g., "10:30 AM"
    person_name: str             # The other person's name
    alternative_times: List[str] # Suggested free times


class MeetingLocationOut(BaseModel):
    """Available meeting location."""
    id: int
    name: str
    venue_name: Optional[str] = None

    class Config:
        from_attributes = True


class CreateMeetingIn(BaseModel):
    """Request to create a meeting."""
    recipient_id: int
    proposed_start: str    # ISO datetime string
    proposed_end: str      # ISO datetime string
    location_id: Optional[int] = None
    message: Optional[str] = None


class MeetingActionIn(BaseModel):
    """Action to take on a meeting request."""
    action: str  # "accept", "decline", "cancel"


class RescheduleMeetingIn(BaseModel):
    """Request to reschedule a meeting."""
    proposed_start: str    # ISO datetime string
    proposed_end: str      # ISO datetime string
    location_id: Optional[int] = None
    message: Optional[str] = None


class MeetingOut(BaseModel):
    """Meeting details for responses."""
    id: int
    requester: ScheduleUserOut
    recipient: ScheduleUserOut
    proposed_start: str    # ISO datetime
    proposed_end: str      # ISO datetime
    status: str
    location: Optional[MeetingLocationOut] = None
    message: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class MeetingsListOut(BaseModel):
    """Categorized list of user's meetings."""
    incoming: List[MeetingOut]    # Requests received
    outgoing: List[MeetingOut]    # Requests sent
    confirmed: List[MeetingOut]   # Confirmed meetings


# -----------------------------
# ONBOARDING
# -----------------------------

class GoalOut(BaseModel):
    """Goal response model."""
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ExperienceLevelOption(BaseModel):
    """Experience level option with label and years range."""
    value: ExperienceLevel
    label: str
    years: str


class DiscussionTopicOption(BaseModel):
    """Discussion topic option with label."""
    value: DiscussionTopic
    label: str


class OnboardingQuestionsOut(BaseModel):
    """All available onboarding options."""
    interests: List[InterestOut]
    goals: List[GoalOut]
    experience_levels: List[ExperienceLevelOption]
    discussion_topics: List[DiscussionTopicOption]


class OnboardingDataOut(BaseModel):
    """User's current onboarding data."""
    status: OnboardingStatus
    interest_ids: List[int]
    goal_ids: List[int]
    experience_level: Optional[ExperienceLevel] = None
    discussion_topics: List[DiscussionTopic]
    completed_at: Optional[str] = None


class OnboardingUpdateIn(BaseModel):
    """Request payload for updating onboarding data."""
    interest_ids: List[int] = Field(default_factory=list)
    goal_ids: List[int] = Field(default_factory=list)
    experience_level: Optional[ExperienceLevel] = None
    discussion_topics: List[DiscussionTopic] = Field(default_factory=list)
    skip: bool = False


# -----------------------------
# POLLS
# -----------------------------

class PollOptionIn(BaseModel):
    """Option text for creating a poll."""
    text: str


class PollCreateIn(BaseModel):
    """Schema for creating a new poll."""
    session_id: Optional[int] = None
    group_id: Optional[int] = None
    question: str
    options: List[str] = Field(..., min_length=2, description="At least 2 options required")


class VoteIn(BaseModel):
    """Schema for voting on a poll."""
    option_id: int


class PollOptionOut(BaseModel):
    """Poll option with vote count."""
    id: int
    text: str
    vote_count: int = 0

    class Config:
        from_attributes = True


class PollOut(BaseModel):
    """Poll with options and user vote status."""
    id: int
    question: str
    session_id: Optional[int] = None
    group_id: Optional[int] = None
    created_by: int
    is_active: bool
    created_at: str  # ISO string
    options: List[PollOptionOut] = []
    user_voted_option_id: Optional[int] = None  # null if user hasn't voted
    total_votes: int = 0

    class Config:
        from_attributes = True


class PollDetailOut(PollOut):
    """Poll with creator info for 'my polls' endpoint."""
    session_title: Optional[str] = None


# -----------------------------
# GROUP MESSAGING
# -----------------------------

class GroupMessageIn(BaseModel):
    """Request to post a message to a group."""
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: GroupMessageType = GroupMessageType.text
    extra_data: Optional[Dict[str, Any]] = None


class GroupMessageSenderOut(BaseModel):
    """Sender info for group messages."""
    id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str  # User's global role

    class Config:
        from_attributes = True


class GroupMessageOut(BaseModel):
    """Response for a single group message."""
    id: int
    group_id: int
    sender: GroupMessageSenderOut
    message_type: str
    content: str
    extra_data: Optional[Dict[str, Any]] = None
    created_at: str  # ISO string

    class Config:
        from_attributes = True


class GroupMessagesListOut(BaseModel):
    """Paginated list of group messages."""
    messages: List[GroupMessageOut]
    total: int
    limit: int
    offset: int


class GroupMemberOut(BaseModel):
    """Group member info."""
    user_id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str  # Group member role (member/admin)
    user_role: str  # User's global role
    joined_at: str  # ISO string

    class Config:
        from_attributes = True


class GroupMembersListOut(BaseModel):
    """List of group members."""
    members: List[GroupMemberOut]
    total: int


class SetGroupMemberRoleIn(BaseModel):
    """Request to set a group member's role."""
    role: GroupMemberRole


# -----------------------------
# SESSION & EXHIBITOR CHAT
# -----------------------------

class ChatMessageIn(BaseModel):
    """Request to post a message to a session or exhibitor chat."""
    content: str = Field(..., min_length=1, max_length=5000)


class ChatMessageSenderOut(BaseModel):
    """Sender info for chat messages."""
    id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


class SessionChatMessageOut(BaseModel):
    """Response for a single session chat message."""
    id: int
    session_id: int
    sender: ChatMessageSenderOut
    content: str
    created_at: str  # ISO string

    class Config:
        from_attributes = True


class SessionChatMessagesListOut(BaseModel):
    """Paginated list of session chat messages."""
    messages: List[SessionChatMessageOut]
    total: int
    limit: int
    offset: int


class ExhibitorChatMessageOut(BaseModel):
    """Response for a single exhibitor chat message."""
    id: int
    exhibitor_id: int
    sender: ChatMessageSenderOut
    content: str
    created_at: str  # ISO string

    class Config:
        from_attributes = True


class ExhibitorChatMessagesListOut(BaseModel):
    """Paginated list of exhibitor chat messages."""
    messages: List[ExhibitorChatMessageOut]
    total: int
    limit: int
    offset: int


# -----------------------------
# QR CODE & POINTS
# -----------------------------

class QrCodeOut(BaseModel):
    """Return the user's id (used as QR value) and current points."""
    user_id: int
    points: int


class ScanIn(BaseModel):
    """Payload when scanning another user's QR code (contains the scanned user's id)."""
    user_id: int


class ScanOut(BaseModel):
    """Response after a successful scan."""
    scan_id: int
    scanned_user_id: int
    scanned_user_name: Optional[str] = None
    points_awarded: int
    scanner_total_points: int
    scanned_total_points: int
    message: str


class ScanLogOut(BaseModel):
    """A single scan-history entry."""
    id: int
    scanner_id: int
    scanner_name: Optional[str] = None
    scanned_id: int
    scanned_name: Optional[str] = None
    points_awarded: int
    created_at: str  # ISO string


class LeaderboardEntryOut(BaseModel):
    """Single entry in the points leaderboard."""
    user_id: int
    full_name: Optional[str] = None
    role: str
    points: int
    rank: int


# -----------------------------
# REWARDS & MILESTONES
# -----------------------------

class PointTransactionOut(BaseModel):
    """Single point transaction entry."""
    id: int
    action_type: str
    points_amount: int
    source_ref: Optional[str] = None
    created_at: str  # ISO string

    class Config:
        from_attributes = True


class RewardsMeOut(BaseModel):
    """Current user's reward status."""
    total_points: int
    current_tier: str
    unlocked_features: List[str]
    recent_transactions: List[PointTransactionOut]


class MilestoneOut(BaseModel):
    """Milestone with achievement status."""
    threshold: int
    feature_key: str
    label: str
    achieved: bool


class ProfileWrapUpOut(BaseModel):
    """Profile wrap-up / festival stats view."""
    greeting: str
    percentile_rank: float
    sessions_attended: int
    total_hours: float
    groups_joined: int
    total_scans: int
    milestone_timeline: List[PointTransactionOut]
    certificate_eligible: bool


class EarnActionOut(BaseModel):
    """Single earning-action definition for the 'How to Earn' list."""
    action_type: str
    label: str
    description: str
    icon: str
    points: int
    repeatable: bool


# -----------------------------
# OUTDOOR MAP (GeoJSON)
# -----------------------------

class OutdoorMapProperties(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    company: Optional[str] = None
    booth_number: Optional[str] = None
    extrusion_height: int = 15

class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    properties: OutdoorMapProperties
    geometry: Dict[str, Any]

class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]

class MapEntityProfileOut(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    company: Optional[str] = None
    is_online: bool = False

    class Config:
        from_attributes = True


# -----------------------------
# LOCATION SHARING
# -----------------------------

class LocationUpdateIn(BaseModel):
    latitude: float
    longitude: float


class LocationSharingToggleIn(BaseModel):
    sharing: bool


class UserLocationOut(BaseModel):
    user_id: int
    full_name: str
    avatar_url: Optional[str] = None
    latitude: float
    longitude: float
    updated_at: str  # ISO string
    group_id: int
    group_color: str  # deterministic hex from group_id

    class Config:
        from_attributes = True


class GroupLocationsOut(BaseModel):
    locations: List[UserLocationOut]
    group_id: int
    group_title: str


class LocationSharingStatusOut(BaseModel):
    group_id: int
    group_title: str
    sharing: bool


# -----------------------------
# PUSH NOTIFICATIONS
# -----------------------------

class PushTokenIn(BaseModel):
    token: str
    platform: Optional[Literal["ios", "android", "web"]] = None


class NotificationOut(BaseModel):
    id: int
    title: str
    body: str
    type: Optional[str] = None
    ref_id: Optional[int] = None
    deeplink: Optional[str] = None
    seen: bool
    created_at: str


class UnseenCountOut(BaseModel):
    count: int


class PreferenceOut(BaseModel):
    category: str
    enabled: bool


class PreferenceUpdateItem(BaseModel):
    category: str
    enabled: bool


# -----------------------------
# VENUE DENSITY
# -----------------------------

class VenueDensityOut(BaseModel):
    venue_id: int
    bucket: str  # green | yellow | orange | red


class DensityResponse(BaseModel):
    venues: list[VenueDensityOut]


# -----------------------------
# GOOGLE CALENDAR
# -----------------------------

class GoogleCallbackIn(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


class GoogleCalendarStatusOut(BaseModel):
    connected: bool
    is_valid: bool = True


# -----------------------------
# TICKETING
# -----------------------------

class TicketPackageOut(BaseModel):
    id: int
    ref_key: str
    name: str
    price_eur: float
    description: Optional[str] = None
    features: list[str] = []
    max_quantity: Optional[int] = None

class CheckoutIn(BaseModel):
    package_id: int

class CheckoutOut(BaseModel):
    checkout_url: str

class TicketOut(BaseModel):
    id: int
    package_id: int
    package_name: str
    qr_code: str       # UUID string — mobile renders this as QR
    status: str        # "active" | "used" | "cancelled"
    created_at: str    # ISO format

class TicketValidateIn(BaseModel):
    qr_code: str

class TicketValidateOut(BaseModel):
    ticket_id: int
    buyer_name: str
    package_name: str
    purchased_at: str
    status: str        # always "valid" on success; error cases return HTTPException


# -----------------------------
# SESSION Q&A
# -----------------------------

class QuestionCreateIn(BaseModel):
    body: str


class QuestionAnswerIn(BaseModel):
    answer_text: str


class QuestionAskerOut(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class QuestionOut(BaseModel):
    id: int
    session_id: int
    body: str
    status: str  # pending | answered | dismissed
    answer_text: Optional[str] = None
    answered_by: Optional[int] = None
    answered_at: Optional[str] = None
    likes_count: int
    liked_by_me: bool
    asker: QuestionAskerOut
    created_at: str

    class Config:
        from_attributes = True


class QuestionListOut(BaseModel):
    questions: List[QuestionOut]
    total: int
    pending_count: int


# -----------------------------
# ADMIN
# -----------------------------

class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_blocked: bool
    points: int = 0
    created_at: str

    class Config:
        from_attributes = True


class PaginatedUsersOut(BaseModel):
    total: int
    offset: int
    limit: int
    items: List[AdminUserOut]


class AuditLogOut(BaseModel):
    id: int
    admin_id: int
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: Optional[Any] = None
    created_at: str

    class Config:
        from_attributes = True


class RoleBreakdownItem(BaseModel):
    role: str
    count: int
    percentage: float

class InterestStatItem(BaseModel):
    name: str
    count: int

class DailyRegistrationItem(BaseModel):
    date: str
    count: int

class AgeGroupItem(BaseModel):
    group: str  # "18-24", "25-34", "35-44", "45+"
    count: int
    percentage: float

class GenderItem(BaseModel):
    gender: str  # "male", "female", "prefer_not_to_say"
    count: int
    percentage: float

class DemographicsOut(BaseModel):
    age_groups: List[AgeGroupItem] = []
    gender_breakdown: List[GenderItem] = []
    sample_size_dob: int = 0
    sample_size_gender: int = 0
    total_users: int = 0

class GroupRankingItem(BaseModel):
    group_id: int
    group_name: str
    count: int

class GroupRankingsOut(BaseModel):
    top_by_members: List[GroupRankingItem] = []
    trending_members: List[GroupRankingItem] = []
    full_ranking: List[GroupRankingItem] = []
    chat_ranking: List[GroupRankingItem] = []
    trending_chats: List[GroupRankingItem] = []

class StatsOut(BaseModel):
    total_users: int
    users_by_role: Dict[str, int]
    role_breakdown: List[RoleBreakdownItem] = []
    total_groups: int
    total_sessions: int
    total_polls: int = 0
    # Interest stats
    top_interests: List[InterestStatItem] = []
    # Group stats
    total_group_memberships: int = 0
    avg_members_per_group: float = 0.0
    # Engagement
    total_dms: int = 0
    total_meetings: int = 0
    total_qr_scans: int = 0
    total_agenda_saves: int = 0
    # Points
    avg_points: float = 0.0
    max_points: int = 0
    users_with_points: int = 0
    # Tickets
    total_tickets: int = 0
    used_tickets: int = 0
    active_tickets: int = 0
    # Reports
    pending_reports: int = 0
    total_reports: int = 0
    # Registration trend (all-time from first registration)
    daily_registrations: List[DailyRegistrationItem] = []
    # Demographics (STAT-02, STAT-03)
    demographics: Optional[DemographicsOut] = None
    # Group rankings (STAT-06 through STAT-10)
    group_rankings: Optional[GroupRankingsOut] = None


class TicketPackageIn(BaseModel):
    name: str
    price_eur: float
    description: Optional[str] = None
    features: list = Field(default_factory=list)
    stripe_price_id: str
    max_quantity: Optional[int] = None
    is_active: bool = True


class TicketPackageUpdateIn(BaseModel):
    name: Optional[str] = None
    price_eur: Optional[float] = None
    description: Optional[str] = None
    features: Optional[list] = None
    max_quantity: Optional[int] = None
    is_active: Optional[bool] = None


class AppConfigOut(BaseModel):
    theme: str
    feature_flags: Dict[str, Any] = {}
    announcement_banner: Optional[str] = None


# -----------------------------
# ADMIN EXTENSIONS
# -----------------------------

class AdminVenueIn(BaseModel):
    key: str = Field(..., max_length=64)
    name: str = Field(..., max_length=200)
    lat: float
    lng: float
    default_zoom: float = 16.0
    has_indoor: bool = True
    category: str = "exhibitor"
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    company: Optional[str] = None
    booth_number: Optional[str] = None
    extrusion_height: int = 15
    sort_order: int = 0
    is_active: bool = True
    capacity: Optional[int] = None
    geojson_geometry: Optional[Dict[str, Any]] = None


class AdminVenueUpdateIn(BaseModel):
    name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    default_zoom: Optional[float] = None
    has_indoor: Optional[bool] = None
    category: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    company: Optional[str] = None
    booth_number: Optional[str] = None
    extrusion_height: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    capacity: Optional[int] = None
    geojson_geometry: Optional[Dict[str, Any]] = None


class AdminVenueOut(BaseModel):
    id: int
    key: str
    name: str
    lat: float
    lng: float
    default_zoom: float
    has_indoor: bool
    category: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    company: Optional[str] = None
    booth_number: Optional[str] = None
    extrusion_height: int
    sort_order: int
    is_active: bool
    capacity: Optional[int] = None
    geojson_geometry: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class AdminFloorIn(BaseModel):
    geojson: Dict[str, Any]


class AdminFloorOut(BaseModel):
    id: int
    venue_id: int
    floor_number: int
    geojson: Dict[str, Any]

    class Config:
        from_attributes = True


class AdminGroupIn(BaseModel):
    group_type: str = Field(..., max_length=50)
    ref_key: str = Field(..., max_length=200)
    title: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    interest_ids: List[int] = Field(default_factory=list)


class AdminGroupUpdateIn(BaseModel):
    group_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    interest_ids: Optional[List[int]] = None


class AdminGroupOut(BaseModel):
    id: int
    group_type: str
    ref_key: str
    title: str
    description: Optional[str] = None
    member_count: int = 0
    created_at: str

    class Config:
        from_attributes = True


class AdminInterestIn(BaseModel):
    name: str = Field(..., max_length=100)


class AdminInterestUpdateIn(BaseModel):
    name: str = Field(..., max_length=100)


class AdminGoalIn(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    display_order: int = 0


class AdminGoalUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None


class AdminGoalOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    display_order: int
    created_at: str

    class Config:
        from_attributes = True


class AdminRoleChangeIn(BaseModel):
    role: UserRole


class BroadcastPushIn(BaseModel):
    title: str
    body: str
    role_filter: Optional[UserRole] = None
    # Phase 13: template-based deeplink (PUSH-01 / T-13-02). The free-text `deeplink`
    # field was removed to close the deeplink-injection threat — admins can no longer
    # type an arbitrary path. Backend resolves the template at send time via
    # app.services.deeplink_resolver.resolve().
    deeplink_template: Literal[
        "none",
        "trending_group",
        "trending_session",
        "biggest_group",
        "biggest_group_chat",
        "biggest_session",
        "leaderboard",
        "schedule",
    ] = "none"
    # Phase 13 gap closure (gap 6c) — age-band targeting.
    # Bucket boundaries match admin demographics dashboard (admin.py:297-304):
    #   18-24 = age <25, 25-34 = age <35, 35-44 = age <45, 45+ = else.
    # IMPORTANT: when age_band != "all", users with date_of_birth IS NULL
    # are EXCLUDED from the broadcast (we cannot determine their band).
    # If the admin needs full reach, leave age_band as "all".
    age_band: Literal["all", "18-24", "25-34", "35-44", "45+"] = "all"


class BroadcastPushOut(BaseModel):
    sent_count: int
    message: str
    # Phase 13 device breakdown (PUSH-04). `unknown_count` covers legacy push tokens
    # that were registered before the platform column existed (Plan 13-02 Pitfall 2).
    total_devices: int = 0
    ios_count: int = 0
    android_count: int = 0
    unknown_count: int = 0
    # Resolved deeplink (string) or null if template was "none" or resolver returned None.
    resolved_deeplink: Optional[str] = None


# -----------------------------
# ENHANCED LEADERBOARD
# -----------------------------

class LeaderboardCategoryEntryOut(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    count: int
    rank: int


class LeaderboardStatsOut(BaseModel):
    points_rank: Optional[int] = None
    sessions_rank: Optional[int] = None
    groups_rank: Optional[int] = None
    scans_rank: Optional[int] = None


class EnhancedLeaderboardOut(BaseModel):
    entries: List[LeaderboardCategoryEntryOut]
    my_entry: Optional[LeaderboardCategoryEntryOut] = None
    my_stats: LeaderboardStatsOut
    category: str
    period: str
    date: Optional[str] = None


# ---- Phase 8: Certification & Journey Timeline ----

class TimelineEventOut(BaseModel):
    type: str
    title: str
    subtitle: Optional[str] = None
    icon: str
    timestamp: str  # ISO string


class TimelineDayOut(BaseModel):
    date: str
    day_label: str
    events: List[TimelineEventOut]


class JourneyTimelineOut(BaseModel):
    days: List[TimelineDayOut]
    total_activities: int


class MilestoneRankOut(BaseModel):
    category: str
    icon: str
    count: int
    rank: int
    total_users: int
    percentile: float
    rank_label: str


class CertificateDataOut(BaseModel):
    user_name: str
    user_avatar_url: Optional[str] = None
    top_milestones: List[MilestoneRankOut]
    all_milestones: List[MilestoneRankOut]
    template: Dict[str, Any]
    template_version: int


# -----------------------------
# GOOGLE WALLET (Phase 13 — GWLT-01, kinded for gap 5b)
# -----------------------------

WalletPassKind = Literal["badge", "ticket"]


class WalletPassIn(BaseModel):
    """Request body for POST /me/wallet/pass/{kind}.

    ticket_id is required when kind='ticket', optional/ignored for kind='badge'.

    NOTE: We deliberately accept only ticket_id (an int) — NOT the qr_code UUID — from
    the client. The route fetches the Ticket row server-side and reads ticket.qr_code
    to use as the wallet-pass barcode value, so the client cannot mint a pass with an
    arbitrary QR string. This is the trust-boundary contract for gap 5b.
    """
    ticket_id: Optional[int] = None


class WalletPassOut(BaseModel):
    """Response from POST /me/wallet/pass/{kind} — signed Save-to-Wallet URL."""
    save_url: str  # https://pay.google.com/gp/v/save/<signed_jwt>
