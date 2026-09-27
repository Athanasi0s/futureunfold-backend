from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, select
from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user_block import UserBlock
from app.api.schemas import SendMessageIn, ConversationOut, ConversationUserOut, MessageOut
from app.services.rewards import award_points
from app.services.config_reader import get_config_value
from app.core.blocking import get_blocked_user_ids

router = APIRouter(dependencies=[require_feature("direct_messages")])

MAX_MESSAGES_PER_DAY = 50

def _sorted_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)

def _is_blocked(db: Session, sender_id: int, recipient_id: int) -> bool:
    # Αμφίδρομος έλεγχος: αν οποιοσδήποτε έχει μπλοκάρει τον άλλο, δεν επιτρέπεται αποστολή.
    block = (
        db.query(UserBlock)
        .filter(
            or_(
                and_(UserBlock.blocker_id == recipient_id, UserBlock.blocked_id == sender_id),
                and_(UserBlock.blocker_id == sender_id, UserBlock.blocked_id == recipient_id),
            )
        )
        .first()
    )
    return block is not None

def _spam_limit_ok(db: Session, sender_id: int) -> bool:
    daily_limit = get_config_value(db, "dm_daily_limit", MAX_MESSAGES_PER_DAY)
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    count = (
        db.query(func.count(Message.id))
        .filter(
            Message.sender_id == sender_id,
            Message.created_at >= start,
            Message.created_at < end,
        )
        .scalar()
    )
    return int(count or 0) < daily_limit

def _get_or_create_conversation(db: Session, user1: int, user2: int) -> tuple[Conversation, bool]:
    """Returns (conversation, is_new). Uses flush — caller must commit."""
    a, b = _sorted_pair(user1, user2)
    convo = db.query(Conversation).filter(Conversation.user_a_id == a, Conversation.user_b_id == b).first()
    if convo:
        return convo, False
    convo = Conversation(user_a_id=a, user_b_id=b)
    db.add(convo)
    db.flush()
    return convo, True

@router.post("/dm/send", response_model=MessageOut)
def send_message(
    payload: SendMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Έλεγχος ότι ο παραλήπτης υπάρχει
    recipient = db.get(User, payload.to_user_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Ο παραλήπτης δεν βρέθηκε.")
    if recipient.id == current_user.id:
        raise HTTPException(status_code=400, detail="Δεν μπορείς να στείλεις μήνυμα στον εαυτό σου.")

    # Block
    if _is_blocked(db, sender_id=current_user.id, recipient_id=recipient.id):
        raise HTTPException(status_code=403, detail="Δεν μπορείς να στείλεις μήνυμα σε αυτόν τον χρήστη (block).")

    # Spam limit
    if not _spam_limit_ok(db, sender_id=current_user.id):
        raise HTTPException(status_code=429, detail="Έφτασες το όριο των 50 μηνυμάτων για σήμερα.")

    convo, _is_new = _get_or_create_conversation(db, current_user.id, recipient.id)

    msg = Message(
        conversation_id=convo.id,
        sender_id=current_user.id,
        recipient_id=recipient.id,
        text=payload.text.strip(),
    )
    if not msg.text:
        raise HTTPException(status_code=400, detail="Το μήνυμα είναι άδειο.")

    db.add(msg)

    # Award networking points — first message in this conversation (ACT-06)
    award_points(db, current_user.id, "NETWORKING", 10, source_ref=str(convo.id))

    db.commit()
    db.refresh(msg)

    return MessageOut(
        id=msg.id,
        sender_id=msg.sender_id,
        recipient_id=msg.recipient_id,
        text=msg.text,
        created_at=msg.created_at.isoformat(),
    )

@router.get("/dm/inbox", response_model=list[ConversationOut])
def inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Βρίσκουμε συνομιλίες όπου συμμετέχει ο χρήστης
    blocked_ids = get_blocked_user_ids(db, current_user.id)
    convos = (
        db.query(Conversation)
        .filter(or_(Conversation.user_a_id == current_user.id, Conversation.user_b_id == current_user.id))
        .order_by(Conversation.id.desc())
        .all()
    )

    out: list[ConversationOut] = []
    for c in convos:
        other_id = c.user_b_id if c.user_a_id == current_user.id else c.user_a_id
        if other_id in blocked_ids:
            continue
        other_user = db.get(User, other_id)
        last = (
            db.query(Message)
            .filter(Message.conversation_id == c.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        out.append(
            ConversationOut(
                id=c.id,
                other_user=ConversationUserOut(
                    id=other_user.id,
                    full_name=other_user.full_name,
                    avatar_url=other_user.avatar_url,
                    role=other_user.role.value if other_user.role else None,
                ),
                last_message=last.text if last else None,
                last_message_at=last.created_at.isoformat() if last else None,
            )
        )
    return out

@router.get("/dm/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    convo = db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Η συνομιλία δεν βρέθηκε.")
    if current_user.id not in (convo.user_a_id, convo.user_b_id):
        raise HTTPException(status_code=403, detail="Δεν έχεις πρόσβαση σε αυτή τη συνομιλία.")

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        MessageOut(
            id=m.id,
            sender_id=m.sender_id,
            recipient_id=m.recipient_id,
            text=m.text,
            created_at=m.created_at.isoformat(),
        )
        for m in msgs
    ]

