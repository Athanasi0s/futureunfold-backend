"""PollOption model for poll answer choices."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PollOption(Base):
    """An option (answer choice) for a poll."""

    __tablename__ = "poll_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)

    # Relationships
    poll = relationship("Poll", back_populates="options")
    answers = relationship(
        "PollAnswer", back_populates="option", lazy="selectin", cascade="all, delete-orphan"
    )
