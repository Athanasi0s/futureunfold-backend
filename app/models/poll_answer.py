"""PollAnswer model for user votes on polls."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PollAnswer(Base):
    """A user's vote on a poll. One vote per user per poll enforced by constraint."""

    __tablename__ = "poll_answers"
    __table_args__ = (
        UniqueConstraint("poll_id", "user_id", name="uq_poll_user_vote"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    poll = relationship("Poll", back_populates="answers")
    option = relationship("PollOption", back_populates="answers")
    user = relationship("User", lazy="joined")
