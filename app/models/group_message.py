from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import ForeignKey, DateTime, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.enums import GroupMessageType


class GroupMessage(Base):
    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(
        String(20),
        default=GroupMessageType.text.value,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Extensible extra data for future message types (e.g., image URLs, file names, thumbnails)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
