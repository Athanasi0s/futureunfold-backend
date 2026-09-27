import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.types import Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.db.base import Base


class TicketStatus(str, enum.Enum):
    active = "active"
    used = "used"
    cancelled = "cancelled"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    package_id = Column(Integer, ForeignKey("ticket_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    stripe_payment_intent_id = Column(String, unique=True, nullable=False, index=True)
    qr_code = Column(String, unique=True, nullable=False, index=True)   # UUID (TICK-08 idempotency key)
    status = Column(
        SQLEnum(TicketStatus, name="ticket_status", native_enum=True),
        nullable=False,
        default=TicketStatus.active,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    package = relationship("TicketPackage", foreign_keys=[package_id])
