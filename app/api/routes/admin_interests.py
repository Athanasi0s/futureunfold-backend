from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.models.interest import Interest
from app.models.user_interest import UserInterest
from app.api.routes.admin import log_admin_action
from app.api.schemas import AdminInterestIn, AdminInterestUpdateIn

router = APIRouter()


# ------------------------------------------------------------------
# 1. GET /admin/interests — list with usage count
# ------------------------------------------------------------------
@router.get("/admin/interests")
def list_interests(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    usage_count = func.count(UserInterest.id).label("usage_count")
    rows = (
        db.query(Interest, usage_count)
        .outerjoin(UserInterest, UserInterest.interest_id == Interest.id)
        .group_by(Interest.id)
        .order_by(Interest.name)
        .all()
    )
    return [
        {
            "id": interest.id,
            "name": interest.name,
            "usage_count": count,
            "created_at": interest.created_at.isoformat() if interest.created_at else "",
        }
        for interest, count in rows
    ]


# ------------------------------------------------------------------
# 2. POST /admin/interests — create interest
# ------------------------------------------------------------------
@router.post("/admin/interests")
def create_interest(
    data: AdminInterestIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Interest).filter(Interest.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Interest name already exists.")
    interest = Interest(name=data.name)
    db.add(interest)
    log_admin_action(
        db, admin.id, "create_interest",
        target_type="interest", detail={"name": data.name},
    )
    db.commit()
    db.refresh(interest)
    return {
        "id": interest.id,
        "name": interest.name,
        "created_at": interest.created_at.isoformat() if interest.created_at else "",
    }


# ------------------------------------------------------------------
# 3. PATCH /admin/interests/{interest_id} — rename
# ------------------------------------------------------------------
@router.patch("/admin/interests/{interest_id}")
def update_interest(
    interest_id: int,
    data: AdminInterestUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    interest = db.get(Interest, interest_id)
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found.")
    # Check name uniqueness
    if data.name != interest.name:
        existing = db.query(Interest).filter(Interest.name == data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Interest name already exists.")
    old_name = interest.name
    interest.name = data.name
    log_admin_action(
        db, admin.id, "update_interest",
        target_type="interest", target_id=interest_id,
        detail={"old_name": old_name, "new_name": data.name},
    )
    db.commit()
    db.refresh(interest)
    return {
        "id": interest.id,
        "name": interest.name,
        "created_at": interest.created_at.isoformat() if interest.created_at else "",
    }


# ------------------------------------------------------------------
# 4. DELETE /admin/interests/{interest_id} — delete
# ------------------------------------------------------------------
@router.delete("/admin/interests/{interest_id}")
def delete_interest(
    interest_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    interest = db.get(Interest, interest_id)
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found.")
    log_admin_action(
        db, admin.id, "delete_interest",
        target_type="interest", target_id=interest_id,
        detail={"name": interest.name},
    )
    db.delete(interest)
    db.commit()
    return {"status": "deleted"}
