"""
Exhibitor model - links Users (with role='exhibitor') to booths/stands.
All user/profile data comes from the User model.
"""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Exhibitor(Base):
    """
    Links users with role='exhibitor' to booths/exhibition spaces.
    Profile data (name, bio, company, etc.) comes from the User table.
    """

    __tablename__ = "exhibitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Required link to users table (exhibitor must have a user account)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Optional booth/stand assignment
    booth_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
