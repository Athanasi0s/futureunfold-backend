from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import UserRole, GroupMemberRole
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.user_interest import UserInterest
from app.api.schemas import GroupOut, GroupsListOut, JoinGroupIn
from app.services.rewards import award_points

router = APIRouter(dependencies=[require_feature("groups")])


def _get_user_interest_ids(db: Session, user_id: int) -> set[int]:
    """Get set of interest IDs for a user."""
    rows = db.execute(
        select(UserInterest.interest_id).where(UserInterest.user_id == user_id)
    ).scalars().all()
    return set(rows)


def _calculate_match_percentage(
    group_interest_ids: set[int],
    user_interest_ids: set[int],
) -> float | None:
    """
    Calculate match percentage based on common interests.
    Returns percentage of user's interests that match the group.
    Returns None if user has no interests.
    """
    if not user_interest_ids:
        return None
    if not group_interest_ids:
        return 0.0
    common = len(group_interest_ids & user_interest_ids)
    return round((common / len(user_interest_ids)) * 100, 1)


def _get_member_count(db: Session, group_id: int) -> int:
    """Get member count for a single group."""
    return db.query(func.count(GroupMember.id)).filter(GroupMember.group_id == group_id).scalar() or 0


def _group_with_count(
    db: Session,
    group: Group,
    user_interest_ids: set[int] | None = None,
) -> dict:
    """Convert a single group to dict with member_count and match_percentage."""
    match_pct = None
    if user_interest_ids is not None:
        group_interest_ids = {i.id for i in group.interests} if group.interests else set()
        match_pct = _calculate_match_percentage(group_interest_ids, user_interest_ids)

    return {
        "id": group.id,
        "group_type": group.group_type,
        "ref_key": group.ref_key,
        "title": group.title,
        "description": group.description,
        "member_count": _get_member_count(db, group.id),
        "match_percentage": match_pct,
    }


def _get_groups_with_count(
    db: Session,
    groups: list[Group],
    user_interest_ids: set[int] | None = None,
) -> list[dict]:
    """Add member_count and match_percentage to a list of groups."""
    if not groups:
        return []
    group_ids = [g.id for g in groups]
    counts = (
        db.query(GroupMember.group_id, func.count(GroupMember.id).label("count"))
        .filter(GroupMember.group_id.in_(group_ids))
        .group_by(GroupMember.group_id)
        .all()
    )
    count_map = {gid: cnt for gid, cnt in counts}

    result = []
    for g in groups:
        match_pct = None
        if user_interest_ids is not None:
            group_interest_ids = {i.id for i in g.interests} if g.interests else set()
            match_pct = _calculate_match_percentage(group_interest_ids, user_interest_ids)

        result.append({
            "id": g.id,
            "group_type": g.group_type,
            "ref_key": g.ref_key,
            "title": g.title,
            "description": g.description,
            "member_count": count_map.get(g.id, 0),
            "match_percentage": match_pct,
        })
    return result


@router.get("/groups", response_model=GroupsListOut)
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search: Optional[str] = Query(None, description="Search in title and description"),
    has_role: Optional[UserRole] = Query(None, description="Filter groups that have members with this role"),
    venue: Optional[str] = Query(None, description="Filter by venue ref_key"),
    limit: int = Query(50, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    List groups with optional filters. Requires authentication.
    - search: case-insensitive search in title and description
    - has_role: filter groups that have at least one member with this role
    - venue: filter by venue ref_key (for venue-type groups)
    - limit/offset: pagination

    Returns match_percentage based on user's interests.
    """
    user_interest_ids = _get_user_interest_ids(db, current_user.id)

    query = db.query(Group).options(selectinload(Group.interests))

    # Search filter (title and description)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Group.title.ilike(search_term)) | (Group.description.ilike(search_term))
        )

    # Venue filter
    if venue:
        query = query.filter(Group.group_type == "venue", Group.ref_key == venue)

    # Has role filter - groups that have at least one member with this role
    if has_role:
        subquery = (
            db.query(GroupMember.group_id)
            .join(User, User.id == GroupMember.user_id)
            .filter(User.role == has_role)
            .distinct()
            .subquery()
        )
        query = query.filter(Group.id.in_(db.query(subquery.c.group_id)))

    # Get total count before pagination
    total = query.count()

    # Apply pagination and ordering
    groups = query.order_by(Group.id.asc()).offset(offset).limit(limit).all()

    return GroupsListOut(
        groups=_get_groups_with_count(db, groups, user_interest_ids),
        total=total,
        limit=limit,
        offset=offset,
    )

@router.post("/groups/join", response_model=GroupOut)
def join_group(
    payload: JoinGroupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = None
    if payload.group_id is not None:
        group = db.query(Group).options(selectinload(Group.interests)).filter(Group.id == payload.group_id).first()
    elif payload.ref_key is not None:
        group = db.query(Group).options(selectinload(Group.interests)).filter(Group.ref_key == payload.ref_key).first()
    else:
        raise HTTPException(status_code=400, detail="Δώσε group_id ή ref_key.")

    if not group:
        raise HTTPException(status_code=404, detail="Το group δεν βρέθηκε.")

    existing = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id)
        .first()
    )

    user_interest_ids = _get_user_interest_ids(db, current_user.id)

    if existing:
        # Ήδη μέλος - επιστρέφουμε το group
        return _group_with_count(db, group, user_interest_ids)

    # Check if this will be the first member (make them admin)
    member_count = _get_member_count(db, group.id)
    role = GroupMemberRole.admin.value if member_count == 0 else GroupMemberRole.member.value

    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role=role))

    # Award points for joining a group (ACT-04)
    award_points(db, current_user.id, "JOIN_GROUP", 20, source_ref=str(group.id))

    db.commit()
    return _group_with_count(db, group, user_interest_ids)

@router.delete("/groups/leave/{group_id}")
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Δεν είσαι μέλος σε αυτό το group.")
    db.delete(member)
    db.commit()
    return {"ok": True}

@router.get("/me/groups", response_model=GroupsListOut)
def my_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search: Optional[str] = Query(None, description="Search in title and description"),
    has_role: Optional[UserRole] = Query(None, description="Filter groups that have members with this role"),
    venue: Optional[str] = Query(None, description="Filter by venue ref_key"),
    limit: int = Query(50, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    List current user's groups with optional filters.
    Returns match_percentage based on user's interests.
    """
    user_interest_ids = _get_user_interest_ids(db, current_user.id)

    query = (
        db.query(Group)
        .options(selectinload(Group.interests))
        .join(GroupMember, GroupMember.group_id == Group.id)
        .filter(GroupMember.user_id == current_user.id)
    )

    # Search filter (title and description)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Group.title.ilike(search_term)) | (Group.description.ilike(search_term))
        )

    # Venue filter
    if venue:
        query = query.filter(Group.group_type == "venue", Group.ref_key == venue)

    # Has role filter - groups that have at least one member with this role
    if has_role:
        subquery = (
            db.query(GroupMember.group_id)
            .join(User, User.id == GroupMember.user_id)
            .filter(User.role == has_role)
            .distinct()
            .subquery()
        )
        query = query.filter(Group.id.in_(db.query(subquery.c.group_id)))

    # Get total count before pagination
    total = query.count()

    # Apply pagination and ordering
    groups = query.order_by(Group.id.asc()).offset(offset).limit(limit).all()

    return GroupsListOut(
        groups=_get_groups_with_count(db, groups, user_interest_ids),
        total=total,
        limit=limit,
        offset=offset,
    )
