from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExhibitorShowcase(Base):
    __tablename__ = "exhibitor_showcases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    exhibitor_id: Mapped[int] = mapped_column(
        ForeignKey("exhibitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    exhibitor = relationship("Exhibitor", foreign_keys=[exhibitor_id])
