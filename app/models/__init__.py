# Κάνουμε import όλα τα models ώστε το Alembic να τα "βλέπει".
from app.models.venue import Venue  # noqa: F401
from app.models.venue_floor import VenueFloor  # noqa: F401
from app.models.map_feature import MapFeature  # noqa: F401

from app.models.user import User  # noqa: F401
from app.models.eventora_magic_link_redemption import EventoraMagicLinkRedemption  # noqa: F401
from app.models.group import Group  # noqa: F401
from app.models.group_member import GroupMember  # noqa: F401
from app.models.group_message import GroupMessage  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.user_block import UserBlock  # noqa: F401
from app.models.user_report import UserReport  # noqa: F401
from app.models.interest import Interest  # noqa: F401
from app.models.user_interest import UserInterest  # noqa: F401
from app.models.group_interest import GroupInterest  # noqa: F401
from app.models.session_interest import SessionInterest  # noqa: F401

# Program & Sessions (Speaker/Exhibitor tables deprecated - use User.role instead)
from app.models.session import Session  # noqa: F401
from app.models.speaker import Speaker  # noqa: F401
from app.models.session_speaker import SessionSpeaker  # noqa: F401
from app.models.user_agenda import UserAgenda  # noqa: F401

# Meetings & Scheduling
from app.models.meeting import Meeting  # noqa: F401

# Onboarding
from app.models.goal import Goal  # noqa: F401
from app.models.user_goal import UserGoal  # noqa: F401
from app.models.user_onboarding import UserOnboarding  # noqa: F401

# Polls (session-linked voting)
from app.models.poll import Poll  # noqa: F401
from app.models.poll_option import PollOption  # noqa: F401
from app.models.poll_answer import PollAnswer  # noqa: F401

# Exhibitors
from app.models.exhibitor import Exhibitor  # noqa: F401

# Exhibitor whitelist
from app.models.exhibitor_whitelist import ExhibitorWhitelist  # noqa: F401

# Exhibitor staff
from app.models.exhibitor_staff import ExhibitorStaff  # noqa: F401

# Exhibitor product showcases
from app.models.exhibitor_showcase import ExhibitorShowcase  # noqa: F401

# Session & Exhibitor chat
from app.models.session_chat_message import SessionChatMessage  # noqa: F401
from app.models.exhibitor_chat_message import ExhibitorChatMessage  # noqa: F401

# QR code scan log
from app.models.scan_log import ScanLog  # noqa: F401

# Rewards point transactions
from app.models.point_transaction import PointTransaction  # noqa: F401

# Location sharing
from app.models.location_share import LocationShare  # noqa: F401

# Push notifications
from app.models.push_token import PushToken  # noqa: F401
from app.models.notification import Notification  # noqa: F401

# Google Calendar
from app.models.google_calendar_token import GoogleCalendarToken  # noqa: F401

# Ticketing
from app.models.ticket_package import TicketPackage  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401

# Session Q&A
from app.models.session_question import SessionQuestion  # noqa: F401
from app.models.session_question_like import SessionQuestionLike  # noqa: F401

# Admin panel
from app.models.app_config import AppConfig  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401

# Smart notifications
from app.models.notification_preference import NotificationPreference  # noqa: F401
from app.models.group_suggestion_sent import GroupSuggestionSent  # noqa: F401

# Leaderboard snapshots
from app.models.leaderboard_snapshot import LeaderboardSnapshot  # noqa: F401

# FestyFirstPhase testing table
from app.models.testing_user_for_first_phase import TestingUserForFirstPhase  # noqa: F401
