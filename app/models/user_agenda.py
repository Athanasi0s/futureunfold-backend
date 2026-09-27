"""
User Agenda model - tracks user's favorited/saved sessions.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserAgenda(Base):
    """
    Join table tracking which sessions a user has saved to their personal agenda.
    """

    __tablename__ = "user_agenda"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_user_agenda"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships for easy access
    user = relationship("User", lazy="joined")
    session = relationship("Session", lazy="joined")
