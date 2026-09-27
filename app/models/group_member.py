from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.enums import GroupMemberRole

class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        default=GroupMemberRole.member.value,
        nullable=False,
    )

    sharing_location: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
