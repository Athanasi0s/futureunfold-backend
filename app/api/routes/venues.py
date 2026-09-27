from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.deps import get_db, require_feature
from app.api.schemas import VenueOut, VenueFloorOut, GeoJsonOut, GeoJSONFeatureCollection, GeoJSONFeature, OutdoorMapProperties, MapEntityProfileOut
from app.models.venue import Venue
from app.models.venue_floor import VenueFloor

router = APIRouter(dependencies=[require_feature("map")])

@router.get("/venues", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db)):
    """Επιστρέφει όλα τα venues για να μπουν ως pins στον outdoor χάρτη."""
    rows = db.execute(select(Venue).order_by(Venue.name)).scalars().all()
    return rows

@router.get("/venues/{venue_id}/floors", response_model=list[VenueFloorOut])
def list_floors(venue_id: int, db: Session = Depends(get_db)):
    """Επιστρέφει τους ορόφους ενός venue."""
    floors = db.execute(
        select(VenueFloor).where(VenueFloor.venue_id == venue_id).order_by(VenueFloor.floor_number)
    ).scalars().all()
    if not floors:
        # αν δεν βρούμε τίποτα, μπορεί να σημαίνει λάθος venue_id
        venue = db.get(Venue, venue_id)
        if venue is None:
            raise HTTPException(status_code=404, detail="Δεν βρέθηκε venue")
    return floors

@router.get("/venues/{venue_id}/floors/{floor_number}/geojson", response_model=GeoJsonOut)
def get_floor_geojson(venue_id: int, floor_number: int, db: Session = Depends(get_db)):
    """Επιστρέφει το GeoJSON ενός συγκεκριμένου ορόφου."""
    floor = db.execute(
        select(VenueFloor).where(
            VenueFloor.venue_id == venue_id,
            VenueFloor.floor_number == floor_number,
        )
    ).scalar_one_or_none()

    if floor is None:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε αυτός ο όροφος")

    return GeoJsonOut(venue_id=venue_id, floor_number=floor_number, geojson=floor.geojson)


@router.get("/outdoor-map", response_model=GeoJSONFeatureCollection)
def get_outdoor_map(db: Session = Depends(get_db)):
    """Returns all active outdoor map entities as a GeoJSON FeatureCollection."""
    venues = db.execute(
        select(Venue)
        .where(Venue.is_active == True, Venue.geojson_geometry.isnot(None))
        .order_by(Venue.sort_order)
    ).scalars().all()

    features = []
    for v in venues:
        features.append(GeoJSONFeature(
            properties=OutdoorMapProperties(
                id=v.id, name=v.name, category=v.category,
                description=v.description, avatar_url=v.avatar_url,
                company=v.company, booth_number=v.booth_number,
                extrusion_height=v.extrusion_height,
            ),
            geometry=v.geojson_geometry,
        ))
    return GeoJSONFeatureCollection(features=features)


@router.get("/venues/{venue_id}/profile", response_model=MapEntityProfileOut)
def get_venue_profile(venue_id: int, db: Session = Depends(get_db)):
    """Returns full profile for a map entity (outdoor map detail view)."""
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue
