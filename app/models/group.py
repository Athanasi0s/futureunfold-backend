from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Π.χ. topic / exhibitor / speaker / session / interest
    group_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Ένα κλειδί που δείχνει σε ποιο αντικείμενο αντιστοιχεί το group
    # π.χ. "topic:ai-deeptech" ή "venue:piraeus_tower" ή "interest:fintech"
    ref_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    interests = relationship(
        "Interest",
        secondary="group_interests",
        lazy="selectin",
    )
