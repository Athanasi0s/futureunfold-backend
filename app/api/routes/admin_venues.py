from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.models.venue import Venue
from app.models.venue_floor import VenueFloor
from app.api.routes.admin import log_admin_action
from app.api.schemas import (
    AdminVenueIn,
    AdminVenueUpdateIn,
    AdminVenueOut,
    AdminFloorIn,
    AdminFloorOut,
)

router = APIRouter()


# ------------------------------------------------------------------
# 1. GET /admin/venues — list all venues
# ------------------------------------------------------------------
@router.get("/admin/venues", response_model=list[AdminVenueOut])
def list_venues(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(Venue)
    if search:
        pattern = f"%{search}%"
        q = q.filter(Venue.name.ilike(pattern))
    venues = q.order_by(Venue.sort_order, Venue.name).all()
    return venues


# ------------------------------------------------------------------
# 2. POST /admin/venues — create venue
# ------------------------------------------------------------------
@router.post("/admin/venues", response_model=AdminVenueOut)
def create_venue(
    data: AdminVenueIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Venue).filter(Venue.key == data.key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Venue key already exists.")
    venue = Venue(**data.model_dump())
    db.add(venue)
    log_admin_action(
        db, admin.id, "create_venue",
        target_type="venue", detail={"key": data.key, "name": data.name},
    )
    db.commit()
    db.refresh(venue)
    return venue


# ------------------------------------------------------------------
# 3. PATCH /admin/venues/{venue_id} — update venue
# ------------------------------------------------------------------
@router.patch("/admin/venues/{venue_id}", response_model=AdminVenueOut)
def update_venue(
    venue_id: int,
    data: AdminVenueUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(venue, field, value)
    log_admin_action(
        db, admin.id, "update_venue",
        target_type="venue", target_id=venue_id, detail=updates,
    )
    db.commit()
    db.refresh(venue)
    return venue


# ------------------------------------------------------------------
# 4. DELETE /admin/venues/{venue_id} — delete venue
# ------------------------------------------------------------------
@router.delete("/admin/venues/{venue_id}")
def delete_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    log_admin_action(
        db, admin.id, "delete_venue",
        target_type="venue", target_id=venue_id,
        detail={"key": venue.key, "name": venue.name},
    )
    db.delete(venue)
    db.commit()
    return {"status": "deleted"}


# ------------------------------------------------------------------
# 5. GET /admin/venues/{venue_id}/floors — list floors
# ------------------------------------------------------------------
@router.get("/admin/venues/{venue_id}/floors", response_model=list[AdminFloorOut])
def list_floors(
    venue_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    floors = (
        db.query(VenueFloor)
        .filter(VenueFloor.venue_id == venue_id)
        .order_by(VenueFloor.floor_number)
        .all()
    )
    return floors


# ------------------------------------------------------------------
# 6. POST /admin/venues/{venue_id}/floors — create floor
# ------------------------------------------------------------------
@router.post("/admin/venues/{venue_id}/floors", response_model=AdminFloorOut)
def create_floor(
    venue_id: int,
    data: AdminFloorIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    venue = db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    # Auto-increment floor_number
    max_floor = (
        db.query(func.max(VenueFloor.floor_number))
        .filter(VenueFloor.venue_id == venue_id)
        .scalar()
    )
    next_floor = (max_floor or 0) + 1
    floor = VenueFloor(
        venue_id=venue_id,
        floor_number=next_floor,
        geojson=data.geojson,
    )
    db.add(floor)
    log_admin_action(
        db, admin.id, "create_floor",
        target_type="venue_floor", target_id=venue_id,
        detail={"floor_number": next_floor},
    )
    db.commit()
    db.refresh(floor)
    return floor


# ------------------------------------------------------------------
# 7. PUT /admin/venues/{venue_id}/floors/{floor_number} — replace floor GeoJSON
# ------------------------------------------------------------------
@router.put("/admin/venues/{venue_id}/floors/{floor_number}", response_model=AdminFloorOut)
def update_floor(
    venue_id: int,
    floor_number: int,
    data: AdminFloorIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    floor = (
        db.query(VenueFloor)
        .filter(VenueFloor.venue_id == venue_id, VenueFloor.floor_number == floor_number)
        .first()
    )
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found.")
    floor.geojson = data.geojson
    log_admin_action(
        db, admin.id, "update_floor",
        target_type="venue_floor", target_id=venue_id,
        detail={"floor_number": floor_number},
    )
    db.commit()
    db.refresh(floor)
    return floor


# ------------------------------------------------------------------
# 8. DELETE /admin/venues/{venue_id}/floors/{floor_number} — delete floor
# ------------------------------------------------------------------
@router.delete("/admin/venues/{venue_id}/floors/{floor_number}")
def delete_floor(
    venue_id: int,
    floor_number: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    floor = (
        db.query(VenueFloor)
        .filter(VenueFloor.venue_id == venue_id, VenueFloor.floor_number == floor_number)
        .first()
    )
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found.")
    log_admin_action(
        db, admin.id, "delete_floor",
        target_type="venue_floor", target_id=venue_id,
        detail={"floor_number": floor_number},
    )
    db.delete(floor)
    db.commit()
    return {"status": "deleted"}
