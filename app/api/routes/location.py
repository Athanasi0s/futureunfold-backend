from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.location_share import LocationShare
from app.api.schemas import (
    LocationUpdateIn,
    LocationSharingToggleIn,
    UserLocationOut,
    GroupLocationsOut,
    LocationSharingStatusOut,
)

router = APIRouter(dependencies=[require_feature("location_sharing")])

# Deterministic color palette for groups
_GROUP_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#F1948A", "#82E0AA", "#F8C471", "#AED6F1", "#D7BDE2",
    "#A3E4D7", "#FAD7A0", "#A9CCE3", "#D5F5E3", "#FADBD8",
]


def _group_color(group_id: int) -> str:
    return _GROUP_COLORS[group_id % len(_GROUP_COLORS)]


def _verify_membership(db: Session, user_id: int, group_id: int) -> GroupMember:
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    return member


@router.put("/groups/{group_id}/location-sharing")
def toggle_location_sharing(
    group_id: int,
    body: LocationSharingToggleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle location sharing for current user in a group."""
    member = _verify_membership(db, current_user.id, group_id)
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    member.sharing_location = body.sharing

    if body.sharing:
        # Upsert LocationShare row with default coords (0,0) until first location update
        existing = db.query(LocationShare).filter(
            LocationShare.user_id == current_user.id,
            LocationShare.group_id == group_id,
        ).first()
        if not existing:
            location_share = LocationShare(
                user_id=current_user.id,
                group_id=group_id,
                latitude=0.0,
                longitude=0.0,
            )
            db.add(location_share)
    else:
        # Remove LocationShare row
        db.query(LocationShare).filter(
            LocationShare.user_id == current_user.id,
            LocationShare.group_id == group_id,
        ).delete()

    # Create system message in group chat
    action = "started" if body.sharing else "stopped"
    system_msg = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        message_type="system",
        content=f"{current_user.full_name} {action} sharing their location",
        extra_data={"type": "location_sharing", "enabled": body.sharing},
    )
    db.add(system_msg)
    db.commit()

    return {"sharing": body.sharing}


@router.put("/me/location")
def update_my_location(
    body: LocationUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update current user's location across all active shares."""
    now = datetime.now(timezone.utc)
    updated = db.query(LocationShare).filter(
        LocationShare.user_id == current_user.id,
    ).update({
        LocationShare.latitude: body.latitude,
        LocationShare.longitude: body.longitude,
        LocationShare.updated_at: now,
    })
    db.commit()

    return {"updated_groups": updated}


@router.get("/groups/{group_id}/locations", response_model=GroupLocationsOut)
def get_group_locations(
    group_id: int,
    max_age_minutes: int = Query(default=10, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all sharing members' locations in a group."""
    _verify_membership(db, current_user.id, group_id)

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    # Also clean up very old shares (>4h) while we're at it
    expiry_cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    db.query(LocationShare).filter(
        LocationShare.group_id == group_id,
        LocationShare.updated_at < expiry_cutoff,
    ).delete()

    # Fetch active locations with user info
    results = (
        db.query(LocationShare, User)
        .join(User, LocationShare.user_id == User.id)
        .join(GroupMember, (
            (GroupMember.user_id == LocationShare.user_id) &
            (GroupMember.group_id == LocationShare.group_id)
        ))
        .filter(
            LocationShare.group_id == group_id,
            GroupMember.sharing_location == True,
            LocationShare.updated_at >= cutoff,
            LocationShare.latitude != 0.0,  # Exclude default coords
        )
        .all()
    )

    color = _group_color(group_id)
    locations = [
        UserLocationOut(
            user_id=loc.user_id,
            full_name=user.full_name or "Unknown",
            avatar_url=user.avatar_url,
            latitude=loc.latitude,
            longitude=loc.longitude,
            updated_at=loc.updated_at.isoformat(),
            group_id=group_id,
            group_color=color,
        )
        for loc, user in results
    ]

    db.commit()  # Commit the cleanup delete

    return GroupLocationsOut(
        locations=locations,
        group_id=group_id,
        group_title=group.title,
    )


@router.get("/me/location-sharing", response_model=list[LocationSharingStatusOut])
def get_my_location_sharing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all groups where current user is sharing location."""
    memberships = (
        db.query(GroupMember, Group)
        .join(Group, GroupMember.group_id == Group.id)
        .filter(
            GroupMember.user_id == current_user.id,
            GroupMember.sharing_location == True,
        )
        .all()
    )

    return [
        LocationSharingStatusOut(
            group_id=member.group_id,
            group_title=group.title,
            sharing=True,
        )
        for member, group in memberships
    ]
