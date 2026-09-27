from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExhibitorStaff(Base):
    __tablename__ = "exhibitor_staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    exhibitor_id: Mapped[int] = mapped_column(
        ForeignKey("exhibitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    exhibitor = relationship("Exhibitor", foreign_keys=[exhibitor_id])
