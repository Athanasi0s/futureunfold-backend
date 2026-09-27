"""
ScanLog model — records every QR-code scan between two users.
When an exhibitor scans an attendee the system awards +10 points.
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The user who performed the scan
    scanner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The user whose QR code was scanned
    scanned_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Points awarded in this scan (0 if no award applies)
    points_awarded = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Prevent the same scanner→scanned pair from being logged more than once
    __table_args__ = (
        UniqueConstraint("scanner_id", "scanned_id", name="uq_scan_pair"),
    )

    # Relationships
    scanner = relationship("User", foreign_keys=[scanner_id], lazy="joined")
    scanned = relationship("User", foreign_keys=[scanned_id], lazy="joined")
