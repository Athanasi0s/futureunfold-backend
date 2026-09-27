from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.user_block import UserBlock


def get_blocked_user_ids(db: Session, user_id: int) -> set[int]:
    """
    Get all user IDs that are involved in a block relationship with the given user.
    Returns IDs of users who blocked this user OR whom this user has blocked.
    """
    blocks = db.query(UserBlock).filter(
        or_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == user_id)
    ).all()
    ids = set()
    for b in blocks:
        ids.add(b.blocker_id if b.blocker_id != user_id else b.blocked_id)
    return ids
