from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, text

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(String, nullable=False)
    body = Column(String, nullable=False)

    # Notification category: "dm", "meeting", "session", "group", "system", etc.
    type = Column(String, nullable=True, index=True)

    # Optional reference to the triggering resource (message_id, session_id, …)
    ref_id = Column(Integer, nullable=True)

    deeplink = Column(String, nullable=True)

    seen = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
