from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_db, get_current_user, require_feature, require_moderator_scope
from app.core.enums import UserRole
from app.models.exhibitor import Exhibitor
from app.models.exhibitor_showcase import ExhibitorShowcase
from app.models.exhibitor_staff import ExhibitorStaff
from app.models.exhibitor_whitelist import ExhibitorWhitelist
from app.models.user import User

router = APIRouter(dependencies=[require_feature("exhibitors")])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_exhibitor_or_403(user: User, db: Session) -> Exhibitor:
    """Return the Exhibitor record for the logged-in user or raise 403."""
    if user.role != UserRole.exhibitor:
        raise HTTPException(status_code=403, detail="Μόνο για exhibitors.")
    exhibitor = db.query(Exhibitor).filter(Exhibitor.user_id == user.id).first()
    if not exhibitor:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε exhibitor record.")
    return exhibitor


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CheckEmailIn(BaseModel):
    email: EmailStr


class CheckEmailOut(BaseModel):
    allowed: bool


class StaffIn(BaseModel):
    full_name: str
    role: str | None = None
    avatar_url: str | None = None


class StaffOut(BaseModel):
    id: int
    full_name: str
    role: str | None
    avatar_url: str | None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Existing endpoint
# ---------------------------------------------------------------------------

@router.post("/exhibitors/check-email", response_model=CheckEmailOut)
def check_exhibitor_email(
    payload: CheckEmailIn,
    db: Session = Depends(get_db),
):
    """Check if an email is in the exhibitor whitelist."""
    email_lower = payload.email.lower()
    exists = db.query(ExhibitorWhitelist).filter(
        ExhibitorWhitelist.email == email_lower
    ).first()
    return CheckEmailOut(allowed=exists is not None)


# ---------------------------------------------------------------------------
# Staff endpoints
# ---------------------------------------------------------------------------

@router.get("/exhibitors/staff", response_model=list[StaffOut], tags=["exhibitors"])
def list_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει το προσωπικό του τρέχοντος exhibitor."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    return db.query(ExhibitorStaff).filter(ExhibitorStaff.exhibitor_id == exhibitor.id).all()


@router.post("/exhibitors/staff", response_model=StaffOut, status_code=201, tags=["exhibitors"])
def add_staff(
    payload: StaffIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Προσθέτει μέλος προσωπικού για τον τρέχοντα exhibitor."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    staff = ExhibitorStaff(
        exhibitor_id=exhibitor.id,
        full_name=payload.full_name,
        role=payload.role,
        avatar_url=payload.avatar_url,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


@router.delete("/exhibitors/staff/{staff_id}", status_code=204, tags=["exhibitors"])
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Διαγράφει μέλος προσωπικού (μόνο ο ιδιοκτήτης exhibitor)."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    staff = db.query(ExhibitorStaff).filter(
        ExhibitorStaff.id == staff_id,
        ExhibitorStaff.exhibitor_id == exhibitor.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Το μέλος προσωπικού δεν βρέθηκε.")
    db.delete(staff)
    db.commit()


# ---------------------------------------------------------------------------
# Showcase schemas
# ---------------------------------------------------------------------------

class ShowcaseIn(BaseModel):
    title: str
    icon_url: str | None = None
    visible: bool = True


class ShowcaseOut(BaseModel):
    id: int
    title: str
    icon_url: str | None
    visible: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Showcase endpoints
# ---------------------------------------------------------------------------

@router.get("/exhibitors/showcases", response_model=list[ShowcaseOut], tags=["exhibitors"])
def list_showcases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει τα product showcases του τρέχοντος exhibitor."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    return db.query(ExhibitorShowcase).filter(ExhibitorShowcase.exhibitor_id == exhibitor.id).all()


@router.post("/exhibitors/showcases", response_model=ShowcaseOut, status_code=201, tags=["exhibitors"])
def add_showcase(
    payload: ShowcaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Προσθέτει product showcase για τον τρέχοντα exhibitor."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    showcase = ExhibitorShowcase(
        exhibitor_id=exhibitor.id,
        title=payload.title,
        icon_url=payload.icon_url,
        visible=payload.visible,
    )
    db.add(showcase)
    db.commit()
    db.refresh(showcase)
    return showcase


@router.delete("/exhibitors/showcases/{showcase_id}", status_code=204, tags=["exhibitors"])
def delete_showcase(
    showcase_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Διαγράφει product showcase (μόνο ο ιδιοκτήτης exhibitor)."""
    exhibitor = _get_exhibitor_or_403(current_user, db)
    showcase = db.query(ExhibitorShowcase).filter(
        ExhibitorShowcase.id == showcase_id,
        ExhibitorShowcase.exhibitor_id == exhibitor.id,
    ).first()
    if not showcase:
        raise HTTPException(status_code=404, detail="Το showcase δεν βρέθηκε.")
    db.delete(showcase)
    db.commit()


# ---------------------------------------------------------------------------
# Admin exhibitor picker (Phase 12 D-20)
# ---------------------------------------------------------------------------

class AdminExhibitorOut(BaseModel):
    """Exhibitor list entry for the admin Session-form EntityPicker (Phase 12 D-20).

    Uses the linked User's full_name as the display label (Exhibitor rows only
    carry booth_code; profile data lives on the user). No sensitive fields —
    response is deliberately minimal.
    """
    id: int
    full_name: str
    booth_code: str | None = None
    company: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


@router.get("/admin/exhibitors", response_model=list[AdminExhibitorOut], tags=["admin"])
def list_exhibitors_admin(
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """List all exhibitors for admin pickers (Phase 12 D-20).

    Gated by `manage_sessions` so the Session-form EntityPicker (Plan 03)
    can read it. Search matches the linked user's full_name case-insensitively.
    """
    q = (
        select(Exhibitor)
        .options(joinedload(Exhibitor.user))
        .join(User, Exhibitor.user_id == User.id)
        .order_by(User.full_name)
    )
    if search:
        like = f"%{search}%"
        q = q.where(User.full_name.ilike(like))
    rows = db.execute(q).scalars().all()
    return [
        AdminExhibitorOut(
            id=exh.id,
            full_name=exh.user.full_name or "Unknown",
            booth_code=exh.booth_code,
            company=exh.user.company,
            avatar_url=exh.user.avatar_url,
        )
        for exh in rows
    ]
