from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint

from app.db.base import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_notif_pref"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(30), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
