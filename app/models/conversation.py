from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # Ένα ζευγάρι χρηστών να έχει μία μόνο συνομιλία.
        UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Κρατάμε το ζευγάρι ταξινομημένο (μικρότερο id -> user_a)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
