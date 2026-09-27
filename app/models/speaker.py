"""
Speaker model - links Users (with role='speaker') to Sessions.
All user/profile data comes from the User model.
"""

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Speaker(Base):
    """
    Legacy table for speaker-session relationships.
    In the new design, this just maps user_id to sessions.
    All profile data (name, bio, photo, etc.) comes from the User table.
    """

    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Required link to users table (speaker must have a user account)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    # Note: Session.speakers now links directly to User via session_speakers.user_id
    # To get a speaker's sessions, query via User.id through session_speakers
