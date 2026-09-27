"""
Polls API routes for session-linked or group-linked interactive voting.

Endpoints:
- POST /polls              Create a new poll (SPEAKER/EXHIBITOR for sessions; any member for groups)
- POST /polls/{poll_id}/vote   Vote on a poll (authenticated users)
- GET  /polls/my           Get polls created by current user (SPEAKER/EXHIBITOR)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.schemas import PollCreateIn, PollOut, PollDetailOut, PollOptionOut, VoteIn
from app.core.deps import get_db, get_current_user, require_feature
from app.services.rewards import award_points
from app.core.enums import UserRole, GroupMessageType
from app.models.poll import Poll
from app.models.poll_option import PollOption
from app.models.poll_answer import PollAnswer
from app.models.session import Session as SessionModel
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage as GroupMessageModel

router = APIRouter(dependencies=[require_feature("polls")])


def _poll_to_out(poll: Poll, current_user_id: int | None = None) -> dict:
    """Convert Poll model to response dict with vote counts and user vote status."""
    # Calculate vote counts per option
    option_vote_counts = {}
    user_voted_option_id = None
    total_votes = 0

    for answer in poll.answers:
        option_vote_counts[answer.option_id] = option_vote_counts.get(answer.option_id, 0) + 1
        total_votes += 1
        if current_user_id and answer.user_id == current_user_id:
            user_voted_option_id = answer.option_id

    options = [
        {
            "id": opt.id,
            "text": opt.text,
            "vote_count": option_vote_counts.get(opt.id, 0),
        }
        for opt in poll.options
    ]

    return {
        "id": poll.id,
        "question": poll.question,
        "session_id": poll.session_id,
        "group_id": poll.group_id,
        "created_by": poll.created_by,
        "is_active": poll.is_active,
        "created_at": poll.created_at.isoformat(),
        "options": options,
        "user_voted_option_id": user_voted_option_id,
        "total_votes": total_votes,
    }


@router.post("/polls", response_model=PollOut)
def create_poll(
    payload: PollCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new poll for a session or group.
    - Session polls: Only SPEAKER, EXHIBITOR, or ADMIN.
    - Group polls: Any group member.
    """
    # XOR validation: exactly one of session_id or group_id must be set
    if payload.session_id is None and payload.group_id is None:
        raise HTTPException(
            status_code=400,
            detail="Either session_id or group_id must be provided.",
        )
    if payload.session_id is not None and payload.group_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Only one of session_id or group_id may be set.",
        )

    if payload.group_id is not None:
        # Group poll: any group member can create
        group = db.get(Group, payload.group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")

        membership = (
            db.query(GroupMember)
            .filter(
                GroupMember.group_id == payload.group_id,
                GroupMember.user_id == current_user.id,
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=403,
                detail="You must be a group member to create a poll in this group.",
            )
    else:
        # Session poll: only speaker/exhibitor/admin
        if current_user.role not in [UserRole.speaker, UserRole.exhibitor, UserRole.admin]:
            raise HTTPException(
                status_code=403,
                detail="Μόνο speakers, exhibitors και admins μπορούν να δημιουργήσουν polls.",
            )

        session = db.get(SessionModel, payload.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")

    # Create poll
    poll = Poll(
        question=payload.question,
        session_id=payload.session_id,
        group_id=payload.group_id,
        created_by=current_user.id,
    )
    db.add(poll)
    db.flush()  # Get poll.id

    # Create options
    for option_text in payload.options:
        option = PollOption(poll_id=poll.id, text=option_text)
        db.add(option)

    # For group polls: insert a GroupMessage with message_type="poll" so it appears in chat
    if payload.group_id is not None:
        poll_msg = GroupMessageModel(
            group_id=payload.group_id,
            sender_id=current_user.id,
            message_type=GroupMessageType.poll.value,
            content=poll.question,
            extra_data={"poll_id": poll.id},
        )
        db.add(poll_msg)

    db.commit()
    db.refresh(poll)

    return _poll_to_out(poll, current_user.id)


@router.post("/polls/{poll_id}/vote", response_model=PollOut)
def vote_on_poll(
    poll_id: int,
    payload: VoteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Vote on a poll. Updates existing vote if user already voted.
    """
    # Get poll
    poll = db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Το poll δεν βρέθηκε.")

    if not poll.is_active:
        raise HTTPException(status_code=400, detail="Το poll δεν είναι ενεργό.")

    # Verify option exists and belongs to this poll
    option = db.get(PollOption, payload.option_id)
    if not option or option.poll_id != poll_id:
        raise HTTPException(status_code=400, detail="Μη έγκυρη επιλογή για αυτό το poll.")

    # Check for existing vote
    existing_vote = db.execute(
        select(PollAnswer).where(
            PollAnswer.poll_id == poll_id,
            PollAnswer.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if existing_vote:
        # Update existing vote
        existing_vote.option_id = payload.option_id
    else:
        # Create new vote
        vote = PollAnswer(
            poll_id=poll_id,
            option_id=payload.option_id,
            user_id=current_user.id,
        )
        db.add(vote)

        # Award points for first poll vote (ACT-05)
        award_points(db, current_user.id, "POLL_VOTE", 10, source_ref=str(poll_id))

    db.commit()
    db.refresh(poll)

    return _poll_to_out(poll, current_user.id)


@router.get("/polls/my", response_model=list[PollDetailOut])
def get_my_polls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all polls created by the current user.
    Only SPEAKER, EXHIBITOR, or ADMIN can access this endpoint.
    """
    # Role check
    if current_user.role not in [UserRole.speaker, UserRole.exhibitor, UserRole.admin]:
        raise HTTPException(
            status_code=403,
            detail="Μόνο speakers, exhibitors και admins έχουν πρόσβαση.",
        )

    # Get user's polls with session info
    query = (
        select(Poll)
        .where(Poll.created_by == current_user.id)
        .order_by(Poll.created_at.desc())
    )
    polls = db.execute(query).scalars().all()

    result = []
    for poll in polls:
        poll_data = _poll_to_out(poll, current_user.id)
        poll_data["session_title"] = poll.session.title if poll.session else None
        poll_data["group_id"] = poll.group_id
        result.append(poll_data)

    return result


@router.get("/polls/{poll_id}", response_model=PollOut)
def get_poll(
    poll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single poll by ID."""
    poll = db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Το poll δεν βρέθηκε.")

    return _poll_to_out(poll, current_user.id)


@router.delete("/polls/{poll_id}")
def delete_poll(
    poll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deactivate a poll (soft delete).
    Only the creator or an admin can delete.
    """
    poll = db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Το poll δεν βρέθηκε.")

    # Only creator or admin can delete
    if poll.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Δεν έχετε δικαίωμα διαγραφής.")

    poll.is_active = False
    db.commit()

    return {"success": True, "message": "Το poll απενεργοποιήθηκε."}
