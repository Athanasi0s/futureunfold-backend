import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import UserRole, GroupMemberRole, GroupMessageType

BASE64_PATTERN = re.compile(r"^data:[a-z]+/[a-z]+;base64,")
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.api.schemas import (
    GroupMessageIn,
    GroupMessageOut,
    GroupMessagesListOut,
    GroupMessageSenderOut,
    GroupMemberOut,
    GroupMembersListOut,
    SetGroupMemberRoleIn,
)

router = APIRouter(dependencies=[require_feature("group_chat")])


def _get_membership(db: Session, group_id: int, user_id: int) -> GroupMember | None:
    """Get the membership record for a user in a group."""
    return (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
    )


def _is_group_admin(db: Session, group_id: int, user_id: int) -> bool:
    """Check if user is a group admin."""
    membership = _get_membership(db, group_id, user_id)
    return membership is not None and membership.role == GroupMemberRole.admin.value


def _can_delete_message(
    db: Session,
    message: GroupMessage,
    current_user: User,
) -> bool:
    """Check if user can delete a message."""
    # User can delete their own message
    if message.sender_id == current_user.id:
        return True
    # Global admins can delete any message
    if current_user.role == UserRole.admin:
        return True
    # Group admins can delete any message in their group
    if _is_group_admin(db, message.group_id, current_user.id):
        return True
    return False


def _format_message(message: GroupMessage, sender: User) -> dict:
    """Format a message for response."""
    return {
        "id": message.id,
        "group_id": message.group_id,
        "sender": {
            "id": sender.id,
            "full_name": sender.full_name,
            "avatar_url": sender.avatar_url,
            "role": sender.role.value if hasattr(sender.role, "value") else sender.role,
        },
        "message_type": message.message_type,
        "content": message.content,
        "extra_data": message.extra_data,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/groups/{group_id}/messages", response_model=GroupMessagesListOut)
def get_group_messages(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100, description="Max messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
):
    """
    Get messages from a group (paginated).
    User must be a member of the group.
    Messages are ordered by created_at descending (newest first).
    """
    # Check group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # Check user is a member
    membership = _get_membership(db, group_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")

    # Get total count
    total = (
        db.query(func.count(GroupMessage.id))
        .filter(GroupMessage.group_id == group_id)
        .scalar()
    ) or 0

    # Get messages with sender info
    messages_query = (
        db.query(GroupMessage, User)
        .join(User, User.id == GroupMessage.sender_id)
        .filter(GroupMessage.group_id == group_id)
        .order_by(GroupMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    messages = [
        _format_message(msg, sender)
        for msg, sender in messages_query.all()
    ]

    return GroupMessagesListOut(
        messages=messages,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/groups/{group_id}/messages", response_model=GroupMessageOut)
def post_group_message(
    group_id: int,
    payload: GroupMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Post a message to a group.
    User must be a member of the group.
    """
    # Check group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # Check user is a member
    membership = _get_membership(db, group_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")

    # Reject base64 image data — images must be uploaded first and sent as URL paths
    if payload.message_type in (GroupMessageType.image,) and BASE64_PATTERN.match(payload.content):
        raise HTTPException(
            status_code=400,
            detail="Image content must be a URL path, not base64 data.",
        )

    # Create message
    message = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        message_type=payload.message_type.value,
        content=payload.content,
        extra_data=payload.extra_data,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return _format_message(message, current_user)


@router.delete("/groups/{group_id}/messages/{message_id}")
def delete_group_message(
    group_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a message from a group.
    User can delete their own messages.
    Group admins and global admins can delete any message.
    """
    # Check group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # Check user is a member
    membership = _get_membership(db, group_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")

    # Get message
    message = (
        db.query(GroupMessage)
        .filter(GroupMessage.id == message_id, GroupMessage.group_id == group_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    # Check permission
    if not _can_delete_message(db, message, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to delete this message.")

    db.delete(message)
    db.commit()

    return {"ok": True}


@router.get("/groups/{group_id}/members", response_model=GroupMembersListOut)
def get_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all members of a group.
    User must be a member of the group.
    """
    # Check group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # Check user is a member
    membership = _get_membership(db, group_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")

    # Get members with user info
    members_query = (
        db.query(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
    )

    members = []
    for member, user in members_query.all():
        members.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "role": member.role,
            "user_role": user.role.value if hasattr(user.role, "value") else user.role,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        })

    return GroupMembersListOut(
        members=members,
        total=len(members),
    )


@router.put("/groups/{group_id}/members/{user_id}/role")
def set_member_role(
    group_id: int,
    user_id: int,
    payload: SetGroupMemberRoleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set a member's role in a group.
    Only group admins and global admins can change roles.
    """
    # Check group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # Check current user has permission (group admin or global admin)
    is_global_admin = current_user.role == UserRole.admin
    is_group_admin = _is_group_admin(db, group_id, current_user.id)

    if not is_global_admin and not is_group_admin:
        raise HTTPException(status_code=403, detail="Only admins can change member roles.")

    # Get target member
    target_membership = _get_membership(db, group_id, user_id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="User is not a member of this group.")

    # Update role
    target_membership.role = payload.role.value
    db.commit()

    return {"ok": True, "new_role": payload.role.value}
