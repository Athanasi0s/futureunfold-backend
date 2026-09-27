"""
Meeting model for 1-on-1 scheduled meetings between users.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SQLEnum

from app.db.base import Base
from app.core.enums import MeetingStatus


class Meeting(Base):
    """
    Represents a scheduled 1-on-1 meeting between two users.

    Flow:
    1. Requester sends meeting request (status=pending, expires_at set to +120 min)
    2. Recipient accepts/declines
    3. On accept: status=confirmed, location assigned
    4. If no response: cron job sets status=expired after expires_at
    """

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Participants
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Scheduling (UTC timezone-aware)
    proposed_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    proposed_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Status tracking
    status: Mapped[MeetingStatus] = mapped_column(
        SQLEnum(MeetingStatus, name="meeting_status", native_enum=True),
        nullable=False,
        default=MeetingStatus.pending,
    )

    # Temporary hold expiration (120 minutes from creation)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Location - uses existing MapFeature (rooms) for indoor map integration
    # Assigned after both parties confirm the meeting
    map_feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("map_features.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional message from requester
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    requester = relationship(
        "User",
        foreign_keys=[requester_id],
        lazy="joined",
    )
    recipient = relationship(
        "User",
        foreign_keys=[recipient_id],
        lazy="joined",
    )
    map_feature = relationship(
        "MapFeature",
        foreign_keys=[map_feature_id],
        lazy="joined",
    )
