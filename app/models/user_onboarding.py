from datetime import datetime, timezone
from typing import List
from sqlalchemy import ForeignKey, DateTime, String, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.enums import OnboardingStatus, ExperienceLevel


class UserOnboarding(Base):
    __tablename__ = "user_onboarding"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        SQLEnum(ExperienceLevel, name="experience_level_enum"),
        nullable=True,
    )

    discussion_topics: Mapped[List[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    status: Mapped[OnboardingStatus] = mapped_column(
        SQLEnum(OnboardingStatus, name="onboarding_status_enum"),
        default=OnboardingStatus.pending,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
