from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint, func

from app.db.base import Base


class GroupSuggestionSent(Base):
    __tablename__ = "group_suggestions_sent"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_group_suggestion_sent"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
