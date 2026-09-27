"""Seed venue capacities and mock LocationShare entries for density testing."""
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.orm import Session as SASession

from app.db.session import SessionLocal
from app.models.venue import Venue
from app.models.location_share import LocationShare
from app.models.user import User
from app.models.group import Group


CAPACITY_RANGES = {
    "stage": (200, 500),
    "exhibitor": (50, 150),
    "amenity": (30, 100),
    "sponsor": (100, 300),
}

# Density target per bucket as fraction of capacity
BUCKET_TARGETS = [
    ("green", 0.15),    # ~15% capacity
    ("yellow", 0.45),   # ~45% capacity
    ("orange", 0.72),   # ~72% capacity
    ("red", 0.92),      # ~92% capacity
]


def point_in_polygon(lat: float, lng: float, polygon_coords: list) -> bool:
    """Ray-casting algorithm for GeoJSON polygon [lng, lat] format."""
    ring = polygon_coords[0]
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def random_point_in_polygon(coords: list, max_attempts: int = 100) -> tuple[float, float] | None:
    """Generate a random point inside a GeoJSON polygon using rejection sampling."""
    ring = coords[0]
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)

    for _ in range(max_attempts):
        lng = random.uniform(min_lng, max_lng)
        lat = random.uniform(min_lat, max_lat)
        if point_in_polygon(lat, lng, coords):
            return (lat, lng)
    return None


def main():
    db: SASession = SessionLocal()
    try:
        # Get all venues with geojson_geometry
        venues = db.execute(
            select(Venue).where(Venue.geojson_geometry.isnot(None))
        ).scalars().all()

        if not venues:
            print("No venues with geojson_geometry found. Run seed_dummy_map first.")
            return

        # Get available users and groups for LocationShare entries
        users = db.execute(select(User)).scalars().all()
        groups = db.execute(select(Group)).scalars().all()

        if not users or not groups:
            print("No users or groups found. Run seed_users and seed_groups first.")
            return

        user_ids = [u.id for u in users]
        group_ids = [g.id for g in groups]

        # Delete existing LocationShares for idempotency (all are seed data)
        db.execute(delete(LocationShare))
        db.flush()

        # 1. Set capacity on venues
        for venue in venues:
            cap_range = CAPACITY_RANGES.get(venue.category, (50, 150))
            venue.capacity = random.randint(cap_range[0], cap_range[1])

        db.flush()
        print(f"Set capacity on {len(venues)} venues.")

        # 2. Create mock LocationShares distributed across density buckets
        # Distribute venues evenly across 4 buckets
        random.shuffle(venues)
        total_shares = 0
        used_pairs: set[tuple[int, int]] = set()  # Track (user_id, group_id) pairs to respect unique constraint

        for i, venue in enumerate(venues):
            bucket_name, target_ratio = BUCKET_TARGETS[i % len(BUCKET_TARGETS)]
            target_count = max(1, int(venue.capacity * target_ratio))

            coords = venue.geojson_geometry.get("coordinates")
            if not coords:
                continue

            created = 0
            for _ in range(target_count):
                point = random_point_in_polygon(coords)
                if not point:
                    continue

                # Find an unused (user_id, group_id) pair
                found_pair = False
                uid = 0
                gid = 0
                for _ in range(20):  # try up to 20 random combos
                    uid = random.choice(user_ids)
                    gid = random.choice(group_ids)
                    if (uid, gid) not in used_pairs:
                        used_pairs.add((uid, gid))
                        found_pair = True
                        break

                if not found_pair:
                    break  # exhausted unique pairs

                lat, lng = point
                db.add(LocationShare(
                    user_id=uid,
                    group_id=gid,
                    latitude=lat,
                    longitude=lng,
                    updated_at=datetime.now(timezone.utc) + timedelta(days=30),
                ))
                created += 1

            total_shares += created
            print(f"  {venue.name}: {bucket_name} bucket — {created} locations (cap={venue.capacity})")

        db.commit()
        print(f"\nSeed density complete. {len(venues)} venues with capacity, {total_shares} location shares created.")
    finally:
        db.close()


run = main

if __name__ == "__main__":
    run()
