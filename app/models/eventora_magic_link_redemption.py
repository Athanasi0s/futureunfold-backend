from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.db.base import Base


class EventoraMagicLinkRedemption(Base):
    """Server-side replay protection for one-time EVENTORA invitation JWTs."""

    __tablename__ = "eventora_magic_link_redemptions"

    id = Column(Integer, primary_key=True)
    jti_hash = Column(String(64), nullable=False, unique=True, index=True)
    invitation_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    redeemed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
