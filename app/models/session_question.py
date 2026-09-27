"""Session Q&A - question model."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SessionQuestion(Base):
    """A question submitted by an attendee during a session."""

    __tablename__ = "session_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # pending | answered | dismissed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Denormalized likes count — kept in sync by the like/unlike endpoints
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    asker = relationship("User", foreign_keys=[user_id], lazy="joined")
    answerer = relationship("User", foreign_keys=[answered_by], lazy="joined")
    likes = relationship(
        "SessionQuestionLike",
        back_populates="question",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
