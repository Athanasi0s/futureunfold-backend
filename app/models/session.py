"""
Session model for festival program events.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Session(Base):
    """
    Represents a scheduled event in the festival program.
    Types: keynote, workshop, panel, break, networking, etc.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Schedule (UTC timezone-aware)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Session type: keynote, workshop, panel, break, networking
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="session")

    # Venue FK (outdoor location)
    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("venues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional specific room/booth within the venue
    map_feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("map_features.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Slides/materials
    slides_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    slides_unlocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Optional session image (banner/thumbnail)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Soft-cancel (Phase 12 D-01)
    is_cancelled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Optional poll link (for audience interaction)
    poll_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Topic tags as PostgreSQL array (kept for backward compatibility and free-form tags)
    # For recommendation matching, prefer using the `interests` relationship
    topic_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Who created this session (exhibitor or admin)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    venue = relationship("Venue", foreign_keys=[venue_id], lazy="joined")
    map_feature = relationship("MapFeature", foreign_keys=[map_feature_id], lazy="joined")
    # Speakers are Users assigned to this session (via session_speakers join table)
    speakers = relationship(
        "User",
        secondary="session_speakers",
        lazy="selectin",
    )
    # Polls linked to this session
    polls = relationship("Poll", back_populates="session", lazy="selectin")
    # Interests linked to this session (for recommendation matching)
    interests = relationship(
        "Interest",
        secondary="session_interests",
        lazy="selectin",
    )
