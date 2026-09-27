"""
Session Q&A API routes.

Endpoints:
- POST   /sessions/{session_id}/qa                        - Submit a question (auth required)
- GET    /sessions/{session_id}/qa                        - List questions with stats (auth required)
- POST   /sessions/{session_id}/qa/{question_id}/answer   - Answer a question (speaker/exhibitor/admin)
- POST   /sessions/{session_id}/qa/{question_id}/dismiss  - Dismiss a question (speaker/exhibitor/admin)
- POST   /sessions/{session_id}/qa/{question_id}/like     - Toggle like on a question (auth required)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import UserRole
from app.models.user import User
from app.models.session import Session as SessionModel
from app.models.session_speaker import SessionSpeaker
from app.models.session_question import SessionQuestion
from app.models.session_question_like import SessionQuestionLike
from app.api.schemas import (
    QuestionCreateIn,
    QuestionAnswerIn,
    QuestionOut,
    QuestionListOut,
    QuestionAskerOut,
)

router = APIRouter(dependencies=[require_feature("session_qa")])


def _is_session_moderator(db: Session, session: SessionModel, user: User) -> bool:
    """True if the user can moderate Q&A (admin, session creator, or assigned speaker)."""
    if user.role == UserRole.admin:
        return True
    if session.created_by == user.id:
        return True
    # Check if assigned as a speaker for this session
    link = db.execute(
        select(SessionSpeaker).where(
            SessionSpeaker.session_id == session.id,
            SessionSpeaker.user_id == user.id,
        )
    ).scalar_one_or_none()
    return link is not None


def _question_to_out(q: SessionQuestion, current_user_id: int, is_moderator: bool) -> QuestionOut:
    """Convert a SessionQuestion ORM object to QuestionOut schema."""
    liked_by_me = any(like.user_id == current_user_id for like in q.likes)
    return QuestionOut(
        id=q.id,
        session_id=q.session_id,
        body=q.body,
        status=q.status,
        answer_text=q.answer_text if q.status == "answered" else None,
        answered_by=q.answered_by,
        answered_at=q.answered_at.isoformat() if q.answered_at else None,
        likes_count=q.likes_count,
        liked_by_me=liked_by_me,
        asker=QuestionAskerOut(
            user_id=q.asker.id,
            full_name=q.asker.full_name,
            avatar_url=q.asker.avatar_url,
        ),
        created_at=q.created_at.isoformat(),
    )


def _get_session_or_404(db: Session, session_id: int) -> SessionModel:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Η συνεδρία δεν βρέθηκε.")
    return session


def _get_question_or_404(db: Session, question_id: int, session_id: int) -> SessionQuestion:
    question = db.execute(
        select(SessionQuestion).where(
            SessionQuestion.id == question_id,
            SessionQuestion.session_id == session_id,
        )
    ).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Η ερώτηση δεν βρέθηκε.")
    return question


# -----------------------------
# SUBMIT A QUESTION
# -----------------------------

@router.post("/sessions/{session_id}/qa", response_model=QuestionOut, status_code=201)
def create_question(
    session_id: int,
    payload: QuestionCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a question for a session. Any authenticated user can ask."""
    _get_session_or_404(db, session_id)

    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Η ερώτηση δεν μπορεί να είναι κενή.")

    question = SessionQuestion(
        session_id=session_id,
        user_id=current_user.id,
        body=payload.body.strip(),
        status="pending",
    )
    db.add(question)
    db.commit()
    db.refresh(question)

    return _question_to_out(question, current_user.id, is_moderator=False)


# -----------------------------
# LIST QUESTIONS
# -----------------------------

@router.get("/sessions/{session_id}/qa", response_model=QuestionListOut)
def list_questions(
    session_id: int,
    sort: str = Query("newest", description="Sort order: 'newest' or 'likes'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all questions for a session.

    - Dismissed questions are hidden from regular attendees; moderators see all.
    - Sort by 'newest' (default) or 'likes'.
    """
    session = _get_session_or_404(db, session_id)
    moderator = _is_session_moderator(db, session, current_user)

    query = select(SessionQuestion).where(SessionQuestion.session_id == session_id)

    # Hide dismissed questions from non-moderators
    if not moderator:
        query = query.where(SessionQuestion.status != "dismissed")

    if sort == "likes":
        query = query.order_by(SessionQuestion.likes_count.desc(), SessionQuestion.created_at.desc())
    else:
        query = query.order_by(SessionQuestion.created_at.desc())

    questions = db.execute(query).scalars().all()

    total = len(questions)
    pending_count = sum(1 for q in questions if q.status == "pending")

    return QuestionListOut(
        questions=[_question_to_out(q, current_user.id, moderator) for q in questions],
        total=total,
        pending_count=pending_count,
    )


# -----------------------------
# ANSWER A QUESTION
# -----------------------------

@router.post("/sessions/{session_id}/qa/{question_id}/answer", response_model=QuestionOut)
def answer_question(
    session_id: int,
    question_id: int,
    payload: QuestionAnswerIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a question. Only speakers, session creator, or admin can answer."""
    session = _get_session_or_404(db, session_id)

    if not _is_session_moderator(db, session, current_user):
        raise HTTPException(
            status_code=403,
            detail="Μόνο speakers και exhibitors μπορούν να απαντήσουν ερωτήσεις.",
        )

    question = _get_question_or_404(db, question_id, session_id)

    if question.status == "dismissed":
        raise HTTPException(status_code=400, detail="Δεν μπορείτε να απαντήσετε απορριφθείσα ερώτηση.")

    if not payload.answer_text.strip():
        raise HTTPException(status_code=400, detail="Η απάντηση δεν μπορεί να είναι κενή.")

    question.status = "answered"
    question.answer_text = payload.answer_text.strip()
    question.answered_by = current_user.id
    question.answered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(question)

    return _question_to_out(question, current_user.id, is_moderator=True)


# -----------------------------
# DISMISS A QUESTION
# -----------------------------

@router.post("/sessions/{session_id}/qa/{question_id}/dismiss", response_model=QuestionOut)
def dismiss_question(
    session_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss a question. Only speakers, session creator, or admin can dismiss."""
    session = _get_session_or_404(db, session_id)

    if not _is_session_moderator(db, session, current_user):
        raise HTTPException(
            status_code=403,
            detail="Μόνο speakers και exhibitors μπορούν να απορρίψουν ερωτήσεις.",
        )

    question = _get_question_or_404(db, question_id, session_id)

    if question.status == "answered":
        raise HTTPException(status_code=400, detail="Δεν μπορείτε να απορρίψετε ήδη απαντημένη ερώτηση.")

    question.status = "dismissed"
    db.commit()
    db.refresh(question)

    return _question_to_out(question, current_user.id, is_moderator=True)


# -----------------------------
# TOGGLE LIKE
# -----------------------------

@router.post("/sessions/{session_id}/qa/{question_id}/like")
def toggle_like(
    session_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Toggle like on a question.
    Returns {"liked": true} if the like was added, {"liked": false} if removed.
    """
    _get_session_or_404(db, session_id)
    question = _get_question_or_404(db, question_id, session_id)

    existing_like = db.execute(
        select(SessionQuestionLike).where(
            SessionQuestionLike.question_id == question_id,
            SessionQuestionLike.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if existing_like:
        db.delete(existing_like)
        question.likes_count = max(0, question.likes_count - 1)
        db.commit()
        return {"liked": False, "likes_count": question.likes_count}
    else:
        like = SessionQuestionLike(question_id=question_id, user_id=current_user.id)
        db.add(like)
        question.likes_count += 1
        db.commit()
        return {"liked": True, "likes_count": question.likes_count}
