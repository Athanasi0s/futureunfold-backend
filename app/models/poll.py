"""Poll model for session or group-linked interactive voting."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Poll(Base):
    """A poll linked to a session or group."""

    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    session = relationship("Session", back_populates="polls", lazy="joined")
    group = relationship("Group", lazy="joined")
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    options = relationship(
        "PollOption", back_populates="poll", lazy="selectin", cascade="all, delete-orphan"
    )
    answers = relationship(
        "PollAnswer", back_populates="poll", lazy="selectin", cascade="all, delete-orphan"
    )
