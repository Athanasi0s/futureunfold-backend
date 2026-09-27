# backend/app/api/routes/auth.py
from datetime import datetime
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.config import (
    JWT_SECRET,
    ADMIN_EMAILS,
    EVENTORA_MAGIC_LINK_AUDIENCE,
    EVENTORA_MAGIC_LINK_ISSUER,
    EVENTORA_MAGIC_LINK_SECRET,
)
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.models.eventora_magic_link_redemption import EventoraMagicLinkRedemption
from app.models.speaker import Speaker
from app.models.exhibitor import Exhibitor
from app.api.schemas import (
    EventoraMagicLinkIn,
    RegisterIn,
    LoginIn,
    TokenOut,
    MeOut,
    UserUpdateIn,
)
from app.core.enums import UserRole
from app.services.eventora_magic_link import (
    EventoraTokenError,
    decode_eventora_invitation,
)

router = APIRouter()

@router.post("/auth/register", response_model=MeOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    # 1) email unique
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Το email χρησιμοποιείται ήδη.")

    # 2) role: αν δεν δοθεί -> attendee
    role = payload.role or UserRole.attendee

    if role == UserRole.admin and payload.email.lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Email not authorized for admin role.")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
    )
    db.add(user)
    db.flush()  # get user.id before commit

    if role == UserRole.exhibitor:
        db.add(Exhibitor(user_id=user.id))

    db.commit()
    db.refresh(user)

    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        avatar_url=user.avatar_url,
        bio=user.bio,
        company=user.company,
        linkedin_url=user.linkedin_url,
        points=user.points or 0,
        last_seen=user.last_seen.isoformat() if user.last_seen else None,
        created_at=user.created_at.isoformat(),
    )

@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Λάθος email ή κωδικός.")

    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        secret=JWT_SECRET,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/eventora", response_model=TokenOut)
def redeem_eventora_magic_link(
    payload: EventoraMagicLinkIn,
    db: Session = Depends(get_db),
):
    """Redeem a signed, expiring EVENTORA invitation exactly once."""
    if not EVENTORA_MAGIC_LINK_SECRET:
        raise HTTPException(status_code=503, detail="EVENTORA integration is not configured.")

    try:
        invitation = decode_eventora_invitation(
            payload.token,
            secret=EVENTORA_MAGIC_LINK_SECRET,
            issuer=EVENTORA_MAGIC_LINK_ISSUER,
            audience=EVENTORA_MAGIC_LINK_AUDIENCE,
        )
    except EventoraTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    jti_hash = hashlib.sha256(invitation.jti.encode("utf-8")).hexdigest()
    if (
        db.query(EventoraMagicLinkRedemption)
        .filter(EventoraMagicLinkRedemption.jti_hash == jti_hash)
        .first()
    ):
        raise HTTPException(status_code=409, detail="EVENTORA link has already been used.")

    by_invitation = (
        db.query(User)
        .filter(User.eventora_invitation_id == invitation.invitation_id)
        .first()
    )
    by_email = db.query(User).filter(User.email == invitation.email).first()
    if by_invitation and by_email and by_invitation.id != by_email.id:
        raise HTTPException(status_code=409, detail="EVENTORA invitation identity conflict.")

    user = by_invitation or by_email
    if user and user.eventora_invitation_id not in (None, invitation.invitation_id):
        raise HTTPException(status_code=409, detail="Email is linked to another invitation.")

    if user is None:
        user = User(
            email=invitation.email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            full_name=invitation.full_name,
            role=UserRole.attendee,
        )
        db.add(user)
        db.flush()

    user.full_name = invitation.full_name
    user.eventora_invitation_id = invitation.invitation_id
    user.eventora_qr_code = invitation.qr_code
    db.add(
        EventoraMagicLinkRedemption(
            jti_hash=jti_hash,
            invitation_id=invitation.invitation_id,
            user_id=user.id,
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="EVENTORA link or admission QR has already been registered.",
        ) from exc

    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        secret=JWT_SECRET,
    )
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=MeOut)
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Phase 11: moderators receive the shared moderator_permissions map so the
    # mobile admin dashboard can filter cards. Non-moderators receive null.
    from app.core.moderator_permissions import get_moderator_permissions
    mod_perms = (
        get_moderator_permissions(db)
        if current_user.role == UserRole.moderator
        else None
    )
    return MeOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        avatar_url=current_user.avatar_url,
        cover_url=current_user.cover_url,
        bio=current_user.bio,
        company=current_user.company,
        linkedin_url=current_user.linkedin_url,
        points=current_user.points or 0,
        theme_preference=current_user.theme_preference,
        last_seen=current_user.last_seen.isoformat() if current_user.last_seen else None,
        created_at=current_user.created_at.isoformat(),
        date_of_birth=current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
        gender=current_user.gender,
        moderator_permissions=mod_perms,
        eventora_qr_code=current_user.eventora_qr_code,
    )


@router.patch("/me", response_model=MeOut)
def update_me(
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update current user's profile fields."""
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("role") == UserRole.admin and current_user.email.lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Email not authorized for admin role.")

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    VALID_GENDERS = {"male", "female", "prefer_not_to_say"}

    for field, value in update_data.items():
        if field == "full_name":
            if not value or len(value.strip()) < 2:
                raise HTTPException(status_code=400, detail="Το full_name πρέπει να έχει τουλάχιστον 2 χαρακτήρες.")
            current_user.full_name = value
        elif field == "date_of_birth":
            if value is None or value == "":
                current_user.date_of_birth = None
            else:
                try:
                    current_user.date_of_birth = datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date_of_birth format. Use YYYY-MM-DD.")
        elif field == "gender":
            if value is None or value == "":
                current_user.gender = None
            elif value not in VALID_GENDERS:
                raise HTTPException(status_code=400, detail="Invalid gender value. Must be one of: male, female, prefer_not_to_say.")
            else:
                current_user.gender = value
        else:
            setattr(current_user, field, value)

    if update_data.get("role") == UserRole.exhibitor:
        exists = db.query(Exhibitor).filter(Exhibitor.user_id == current_user.id).first()
        if not exists:
            db.add(Exhibitor(user_id=current_user.id))

    db.commit()
    db.refresh(current_user)

    from app.core.moderator_permissions import get_moderator_permissions
    mod_perms = (
        get_moderator_permissions(db)
        if current_user.role == UserRole.moderator
        else None
    )
    return MeOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        avatar_url=current_user.avatar_url,
        cover_url=current_user.cover_url,
        bio=current_user.bio,
        company=current_user.company,
        linkedin_url=current_user.linkedin_url,
        points=current_user.points or 0,
        theme_preference=current_user.theme_preference,
        last_seen=current_user.last_seen.isoformat() if current_user.last_seen else None,
        created_at=current_user.created_at.isoformat(),
        date_of_birth=current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
        gender=current_user.gender,
        moderator_permissions=mod_perms,
        eventora_qr_code=current_user.eventora_qr_code,
    )
