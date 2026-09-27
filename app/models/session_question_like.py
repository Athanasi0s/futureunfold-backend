"""Session Q&A - per-user like tracking."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SessionQuestionLike(Base):
    """Tracks which users liked which questions (one like per user per question)."""

    __tablename__ = "session_question_likes"
    __table_args__ = (
        UniqueConstraint("question_id", "user_id", name="uq_question_user_like"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    question_id: Mapped[int] = mapped_column(
        ForeignKey("session_questions.id", ondelete="CASCADE"), nullable=False, index=True
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
    question = relationship("SessionQuestion", back_populates="likes")
