from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.group_member import GroupMember
from app.models.conversation import Conversation
from app.models.meeting import Meeting
from app.models.scan_log import ScanLog


def get_friend_ids(db: Session, user_id: int) -> set[int]:
    """
    Returns deduplicated set of user IDs who have interacted with user_id.
    Sources: shared group membership, DM conversations, meetings, QR scans.
    """
    result: set[int] = set()

    # Co-members in same groups
    my_groups = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    co_members = (
        select(GroupMember.user_id)
        .where(GroupMember.group_id.in_(my_groups))
        .where(GroupMember.user_id != user_id)
    )
    result.update(db.execute(co_members).scalars().all())

    # DM conversation partners (bidirectional)
    dm_a = select(Conversation.user_b_id).where(Conversation.user_a_id == user_id)
    dm_b = select(Conversation.user_a_id).where(Conversation.user_b_id == user_id)
    result.update(db.execute(dm_a).scalars().all())
    result.update(db.execute(dm_b).scalars().all())

    # Meeting participants (bidirectional)
    meet_a = select(Meeting.recipient_id).where(Meeting.requester_id == user_id)
    meet_b = select(Meeting.requester_id).where(Meeting.recipient_id == user_id)
    result.update(db.execute(meet_a).scalars().all())
    result.update(db.execute(meet_b).scalars().all())

    # QR scan pairs (bidirectional)
    scan_a = select(ScanLog.scanned_id).where(ScanLog.scanner_id == user_id)
    scan_b = select(ScanLog.scanner_id).where(ScanLog.scanned_id == user_id)
    result.update(db.execute(scan_a).scalars().all())
    result.update(db.execute(scan_b).scalars().all())

    result.discard(user_id)
    return result
