from sqlalchemy import Column, Integer, String, Boolean, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base

class TicketPackage(Base):
    __tablename__ = "ticket_packages"

    id = Column(Integer, primary_key=True, index=True)
    ref_key = Column(String, unique=True, nullable=False)        # e.g. "ticket_01"
    name = Column(String, nullable=False)
    price_eur = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)
    features = Column(JSONB, nullable=False, default=list)        # ["Wi-Fi access", "Lunch included"]
    stripe_price_id = Column(String, nullable=False)              # "price_xxx" from Stripe
    max_quantity = Column(Integer, nullable=True)                  # None = unlimited
    is_active = Column(Boolean, nullable=False, default=True)
