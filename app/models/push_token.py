from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, func

from app.db.base import Base


class PushToken(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Expo push token, e.g. ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]
    token = Column(String, nullable=False)
    # Platform emitted by mobile registration: 'ios' | 'android' | 'web' | NULL (legacy rows).
    # Added Phase 13 Plan 02 to power device-breakdown in /admin/push/broadcast response (PUSH-04).
    platform = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_user_push_token"),
    )
