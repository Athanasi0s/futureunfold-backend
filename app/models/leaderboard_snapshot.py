"""
LeaderboardSnapshot model — stores daily precomputed leaderboard data
for all 4 categories (points, sessions, groups, scans).

Snapshots are created by a midnight cron job for the previous day.
"Today" is always computed live from raw data.
"""

from sqlalchemy import Column, Integer, String, Date, ForeignKey, Index, UniqueConstraint

from app.db.base import Base


class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "category", "user_id",
            name="uq_snapshot_date_cat_user",
        ),
        Index("ix_snapshot_date_category", "snapshot_date", "category"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False)
    category = Column(String(20), nullable=False)  # "points", "sessions", "groups", "scans"
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    count = Column(Integer, nullable=False, default=0)
    rank = Column(Integer, nullable=False)
