from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_feature
from app.api.schemas import DensityResponse, VenueDensityOut
from app.models.venue import Venue
from app.models.location_share import LocationShare
from app.services.config_reader import get_config_value

DEFAULT_DENSITY_THRESHOLDS = {"green": 0.30, "yellow": 0.60, "orange": 0.85}

router = APIRouter(dependencies=[require_feature("density")])


def point_in_polygon(lat: float, lng: float, polygon_coords: list) -> bool:
    """Ray-casting algorithm for GeoJSON polygon [lng, lat] format."""
    ring = polygon_coords[0]  # outer ring
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]  # lng, lat
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


@router.get("/venues/density", response_model=DensityResponse)
def get_venue_density(db: Session = Depends(get_db)):
    """Return crowd density bucket per venue. Public endpoint (no auth required)."""
    # Get venues with both capacity and geometry
    venues = db.execute(
        select(Venue).where(
            Venue.capacity.isnot(None),
            Venue.geojson_geometry.isnot(None),
        )
    ).scalars().all()

    if not venues:
        return DensityResponse(venues=[])

    # Get active location shares (updated within last 10 minutes, non-zero coords)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    locations = db.execute(
        select(LocationShare).where(
            LocationShare.updated_at >= cutoff,
            LocationShare.latitude != 0.0,
            LocationShare.longitude != 0.0,
        )
    ).scalars().all()

    thresholds = get_config_value(db, "density_thresholds", DEFAULT_DENSITY_THRESHOLDS)
    green_t = thresholds.get("green", 0.30)
    yellow_t = thresholds.get("yellow", 0.60)
    orange_t = thresholds.get("orange", 0.85)

    result = []
    for venue in venues:
        geom = venue.geojson_geometry
        if not geom or "coordinates" not in geom:
            continue

        coords = geom["coordinates"]
        # Count people inside this venue's polygon
        count = sum(
            1 for loc in locations
            if point_in_polygon(loc.latitude, loc.longitude, coords)
        )

        # Calculate density ratio and map to bucket
        ratio = count / venue.capacity if venue.capacity > 0 else 0.0
        if ratio < green_t:
            bucket = "green"
        elif ratio < yellow_t:
            bucket = "yellow"
        elif ratio < orange_t:
            bucket = "orange"
        else:
            bucket = "red"

        result.append(VenueDensityOut(venue_id=venue.id, bucket=bucket))

    return DensityResponse(venues=result)
