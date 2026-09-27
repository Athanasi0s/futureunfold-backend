from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.config import JWT_SECRET
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.models.testing_user_for_first_phase import TestingUserForFirstPhase
from app.api.schemas import (
    FirstPhaseRegisterIn,
    FirstPhaseUserOut,
    FirstPhaseLoginOut,
    LoginIn,
)

router = APIRouter(prefix="/first-phase/auth", tags=["first-phase-auth"])


def _user_out(user: User) -> FirstPhaseUserOut:
    return FirstPhaseUserOut(id=str(user.id), email=user.email, name=user.full_name or "")


@router.post("/register", response_model=FirstPhaseLoginOut, status_code=201)
def register(payload: FirstPhaseRegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use.")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.name,
    )
    db.add(user)
    db.flush()

    db.add(TestingUserForFirstPhase(user_id=user.id))
    db.commit()
    db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        secret=JWT_SECRET,
    )
    return FirstPhaseLoginOut(token=token, user=_user_out(user))


@router.post("/login", response_model=FirstPhaseLoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Only allow users that have a TestingUserForFirstPhase record
    testing_record = db.query(TestingUserForFirstPhase).filter(
        TestingUserForFirstPhase.user_id == user.id
    ).first()
    if not testing_record:
        raise HTTPException(status_code=403, detail="Account not registered for this app.")

    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        secret=JWT_SECRET,
    )
    return FirstPhaseLoginOut(token=token, user=_user_out(user))


@router.get("/me", response_model=FirstPhaseUserOut)
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    testing_record = db.query(TestingUserForFirstPhase).filter(
        TestingUserForFirstPhase.user_id == current_user.id
    ).first()
    if not testing_record:
        raise HTTPException(status_code=403, detail="Account not registered for this app.")

    return _user_out(current_user)
