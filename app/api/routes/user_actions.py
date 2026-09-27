from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.user_block import UserBlock
from app.models.user_report import UserReport
from app.api.schemas import ReportUserIn

router = APIRouter()


@router.post("/users/{user_id}/report")
def report_user(
    user_id: int,
    payload: ReportUserIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot report yourself")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    # Rate limit: max 10 reports per day
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    report_count = db.query(UserReport).filter(
        UserReport.reporter_id == current_user.id,
        UserReport.created_at >= today_start,
    ).count()
    if report_count >= 10:
        raise HTTPException(429, "Daily report limit reached (max 10)")

    report = UserReport(
        reporter_id=current_user.id,
        reported_id=user_id,
        reason=payload.reason,
        details=payload.details[:500] if payload.details else None,
        status="pending",
    )
    db.add(report)
    db.commit()
    return {"ok": True, "message": "Report submitted"}


@router.post("/users/{user_id}/block")
def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot block yourself")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    existing = db.query(UserBlock).filter_by(
        blocker_id=current_user.id, blocked_id=user_id
    ).first()
    if existing:
        return {"ok": True, "message": "Already blocked"}
    db.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))
    db.commit()
    return {"ok": True, "message": "User blocked"}


@router.delete("/users/{user_id}/block")
def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    block = db.query(UserBlock).filter_by(
        blocker_id=current_user.id, blocked_id=user_id
    ).first()
    if block:
        db.delete(block)
        db.commit()
    return {"ok": True, "message": "User unblocked"}


@router.get("/me/blocked-users")
def get_blocked_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    blocks = db.query(UserBlock).filter(
        UserBlock.blocker_id == current_user.id
    ).all()
    blocked_ids = [b.blocked_id for b in blocks]
    if not blocked_ids:
        return []
    users = db.query(User).filter(User.id.in_(blocked_ids)).all()
    return [
        {"id": u.id, "full_name": u.full_name, "avatar_url": u.avatar_url}
        for u in users
    ]
