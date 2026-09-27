"""
Session-Speaker join table for many-to-many relationship.
Links sessions directly to users (who have role='speaker').
"""

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SessionSpeaker(Base):
    """
    Join table linking Sessions to Users (with role='speaker').
    Uses user_id directly to avoid ID confusion between Speaker.id and User.id.
    Supports multiple speakers per session (panels) and
    multiple sessions per speaker.
    """

    __tablename__ = "session_speakers"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Links directly to users.id (must have role='speaker')
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Distinguish moderators from regular panelists
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
