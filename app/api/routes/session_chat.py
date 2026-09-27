from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import func

from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.session import Session
from app.models.session_chat_message import SessionChatMessage
from app.api.schemas import (
    ChatMessageIn,
    SessionChatMessageOut,
    SessionChatMessagesListOut,
)

router = APIRouter(dependencies=[require_feature("session_chat")])


def _format_message(message: SessionChatMessage, sender: User) -> dict:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "sender": {
            "id": sender.id,
            "full_name": sender.full_name,
            "avatar_url": sender.avatar_url,
            "role": sender.role.value if hasattr(sender.role, "value") else sender.role,
        },
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/sessions/{session_id}/chat", response_model=SessionChatMessagesListOut)
def get_session_chat(
    session_id: int,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100, description="Max messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
):
    """Get messages from a session chat (paginated, newest first)."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    total = (
        db.query(func.count(SessionChatMessage.id))
        .filter(SessionChatMessage.session_id == session_id)
        .scalar()
    ) or 0

    rows = (
        db.query(SessionChatMessage, User)
        .join(User, User.id == SessionChatMessage.sender_id)
        .filter(SessionChatMessage.session_id == session_id)
        .order_by(SessionChatMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    messages = [_format_message(msg, sender) for msg, sender in rows]

    return SessionChatMessagesListOut(
        messages=messages,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/sessions/{session_id}/chat", response_model=SessionChatMessageOut)
def post_session_chat(
    session_id: int,
    payload: ChatMessageIn,
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post a message to a session chat."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    message = SessionChatMessage(
        session_id=session_id,
        sender_id=current_user.id,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return _format_message(message, current_user)
