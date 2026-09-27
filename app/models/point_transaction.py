"""
PointTransaction model — audit log for every point-earning action.
Each row records who earned points, for what action, and which specific
resource triggered it (session, group, poll, etc.).

The unique constraint on (user_id, action_type, source_ref) prevents
duplicate awards for the same action instance.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Action identifier, e.g. "ATTEND_SESSION", "QR_SCAN", "POLL_VOTE"
    action_type = Column(String, nullable=False, index=True)

    # Points awarded in this transaction
    points_amount = Column(Integer, nullable=False)

    # Reference to the triggering resource (session_id, group_id, etc.)
    # Use "0" for one-time actions like ONBOARDING
    source_ref = Column(String, nullable=False, default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # One award per (user, action, source) combination
    __table_args__ = (
        UniqueConstraint("user_id", "action_type", "source_ref", name="uq_user_action_source"),
    )

    # Relationships
    user = relationship("User", lazy="joined")
