from enum import Enum


class UserRole(str, Enum):
    attendee = "attendee"
    speaker = "speaker"
    exhibitor = "exhibitor"
    admin = "admin"
    moderator = "moderator"


class MeetingStatus(str, Enum):
    pending = "pending"      # Request sent, awaiting recipient response
    confirmed = "confirmed"  # Both parties confirmed
    declined = "declined"    # Recipient declined the request
    cancelled = "cancelled"  # Either party cancelled
    expired = "expired"      # Temporary hold expired (120 min timeout)


class OnboardingStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    skipped = "skipped"


class ExperienceLevel(str, Enum):
    beginner = "beginner"          # Just starting out (0-1 years)
    early_stage = "early_stage"    # Early stage (1-3 years)
    experienced = "experienced"    # Experienced (3-7 years)
    expert = "expert"              # Expert/Veteran (7+ years)


class DiscussionTopic(str, Enum):
    fundraising = "fundraising"                      # Fundraising strategies
    product_market_fit = "product_market_fit"        # Product-market fit
    scaling_teams = "scaling_teams"                  # Scaling teams/team building
    go_to_market = "go_to_market"                    # Go-to-market strategies
    technical_architecture = "technical_architecture"  # Technical architecture
    user_acquisition = "user_acquisition"            # User acquisition
    international_expansion = "international_expansion"  # International expansion
    exit_strategies = "exit_strategies"              # Exit strategies
    regulatory_challenges = "regulatory_challenges"  # Regulatory challenges
    custom_input = "custom_input"                    # Custom input
    other = "other"                                  # Other


class GroupMemberRole(str, Enum):
    member = "member"
    admin = "admin"


class GroupMessageType(str, Enum):
    text = "text"
    image = "image"
    pdf = "pdf"
    file = "file"
    system = "system"
    poll = "poll"


class RewardTier(str, Enum):
    explorer = "explorer"
    innovator = "innovator"
    master = "master"
