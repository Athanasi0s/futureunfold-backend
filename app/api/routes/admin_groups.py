from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_interest import GroupInterest
from app.models.interest import Interest
from app.api.routes.admin import log_admin_action
from app.api.schemas import (
    AdminGroupIn,
    AdminGroupUpdateIn,
    AdminGroupOut,
)

router = APIRouter()


def _group_to_out(group: Group, member_count: int) -> AdminGroupOut:
    return AdminGroupOut(
        id=group.id,
        group_type=group.group_type,
        ref_key=group.ref_key,
        title=group.title,
        description=group.description,
        member_count=member_count,
        created_at=group.created_at.isoformat() if group.created_at else "",
    )


# ------------------------------------------------------------------
# 1. GET /admin/groups — list all groups with member count
# ------------------------------------------------------------------
@router.get("/admin/groups")
def list_groups(
    search: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    member_count_sub = (
        func.count(GroupMember.id).label("member_count")
    )
    q = (
        db.query(Group, member_count_sub)
        .outerjoin(GroupMember, GroupMember.group_id == Group.id)
        .group_by(Group.id)
    )
    if search:
        pattern = f"%{search}%"
        q = q.filter(Group.title.ilike(pattern))
    total = q.count()
    rows = q.order_by(Group.created_at.desc()).offset(offset).limit(limit).all()
    items = [_group_to_out(group, count) for group, count in rows]
    return {"total": total, "items": items}


# ------------------------------------------------------------------
# 2. POST /admin/groups — create group
# ------------------------------------------------------------------
@router.post("/admin/groups", response_model=AdminGroupOut)
def create_group(
    data: AdminGroupIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Group).filter(Group.ref_key == data.ref_key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group ref_key already exists.")
    group = Group(
        group_type=data.group_type,
        ref_key=data.ref_key,
        title=data.title,
        description=data.description,
    )
    db.add(group)
    db.flush()

    # Link interest_ids
    if data.interest_ids:
        # Validate interest IDs exist
        existing_ids = set(
            row[0] for row in db.query(Interest.id)
            .filter(Interest.id.in_(data.interest_ids))
            .all()
        )
        for iid in data.interest_ids:
            if iid in existing_ids:
                db.add(GroupInterest(group_id=group.id, interest_id=iid))

    log_admin_action(
        db, admin.id, "create_group",
        target_type="group", detail={"ref_key": data.ref_key, "title": data.title},
    )
    db.commit()
    db.refresh(group)
    return _group_to_out(group, 0)


# ------------------------------------------------------------------
# 3. PATCH /admin/groups/{group_id} — update group
# ------------------------------------------------------------------
@router.patch("/admin/groups/{group_id}", response_model=AdminGroupOut)
def update_group(
    group_id: int,
    data: AdminGroupUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    updates = data.model_dump(exclude_unset=True)

    # Handle interest_ids separately
    interest_ids = updates.pop("interest_ids", None)
    for field, value in updates.items():
        setattr(group, field, value)

    if interest_ids is not None:
        # Replace all group interests
        db.query(GroupInterest).filter(GroupInterest.group_id == group_id).delete()
        existing_ids = set(
            row[0] for row in db.query(Interest.id)
            .filter(Interest.id.in_(interest_ids))
            .all()
        )
        for iid in interest_ids:
            if iid in existing_ids:
                db.add(GroupInterest(group_id=group_id, interest_id=iid))

    log_admin_action(
        db, admin.id, "update_group",
        target_type="group", target_id=group_id, detail=data.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(group)

    member_count = db.query(func.count(GroupMember.id)).filter(GroupMember.group_id == group_id).scalar() or 0
    return _group_to_out(group, member_count)


# ------------------------------------------------------------------
# 4. DELETE /admin/groups/{group_id} — delete group
# ------------------------------------------------------------------
@router.delete("/admin/groups/{group_id}")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    log_admin_action(
        db, admin.id, "delete_group",
        target_type="group", target_id=group_id,
        detail={"ref_key": group.ref_key, "title": group.title},
    )
    db.delete(group)
    db.commit()
    return {"status": "deleted"}
