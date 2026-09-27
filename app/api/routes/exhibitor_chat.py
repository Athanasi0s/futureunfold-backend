from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import UserRole
from app.models.user import User
from app.models.exhibitor_chat_message import ExhibitorChatMessage
from app.api.schemas import (
    ChatMessageIn,
    ExhibitorChatMessageOut,
    ExhibitorChatMessagesListOut,
)

router = APIRouter(dependencies=[require_feature("exhibitor_chat")])


def _get_exhibitor_user(db: Session, user_id: int) -> User | None:
    """Verify the user_id belongs to an exhibitor."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    role = user.role.value if hasattr(user.role, "value") else user.role
    if role != UserRole.exhibitor.value:
        return None
    return user


def _format_message(message: ExhibitorChatMessage, sender: User) -> dict:
    return {
        "id": message.id,
        "exhibitor_id": message.exhibitor_user_id,
        "sender": {
            "id": sender.id,
            "full_name": sender.full_name,
            "avatar_url": sender.avatar_url,
            "role": sender.role.value if hasattr(sender.role, "value") else sender.role,
        },
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/exhibitors/{exhibitor_id}/chat", response_model=ExhibitorChatMessagesListOut)
def get_exhibitor_chat(
    exhibitor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100, description="Max messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
):
    """Get messages from an exhibitor chat (paginated, newest first)."""
    exhibitor = _get_exhibitor_user(db, exhibitor_id)
    if not exhibitor:
        raise HTTPException(status_code=404, detail="Exhibitor not found.")

    total = (
        db.query(func.count(ExhibitorChatMessage.id))
        .filter(ExhibitorChatMessage.exhibitor_user_id == exhibitor_id)
        .scalar()
    ) or 0

    rows = (
        db.query(ExhibitorChatMessage, User)
        .join(User, User.id == ExhibitorChatMessage.sender_id)
        .filter(ExhibitorChatMessage.exhibitor_user_id == exhibitor_id)
        .order_by(ExhibitorChatMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    messages = [_format_message(msg, sender) for msg, sender in rows]

    return ExhibitorChatMessagesListOut(
        messages=messages,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/exhibitors/{exhibitor_id}/chat", response_model=ExhibitorChatMessageOut)
def post_exhibitor_chat(
    exhibitor_id: int,
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post a message to an exhibitor chat."""
    exhibitor = _get_exhibitor_user(db, exhibitor_id)
    if not exhibitor:
        raise HTTPException(status_code=404, detail="Exhibitor not found.")

    message = ExhibitorChatMessage(
        exhibitor_user_id=exhibitor_id,
        sender_id=current_user.id,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return _format_message(message, current_user)
