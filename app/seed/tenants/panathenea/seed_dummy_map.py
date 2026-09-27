"""Seed = γεμίζουμε τη βάση με αρχικά (dummy) δεδομένα.

Τι θα βάλει:
- Venues (pins)
- Floors ανά venue
- GeoJSON ανά floor (απλές κάτοψεις)
- Map Features (booths/rooms) για μελλοντικά highlights

ΣΗΜΑΝΤΙΚΟ: αυτά είναι DUMMY. Αργότερα θα αντικατασταθούν με πραγματικά σχέδια.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.venue import Venue
from app.models.venue_floor import VenueFloor
from app.models.map_feature import MapFeature


def _rectangle(center_lat: float, center_lng: float, dlat: float, dlng: float):
    """Φτιάχνει ορθογώνιο polygon γύρω από ένα κέντρο.
    Επιστρέφει λίστα συντεταγμένων [lng, lat] κλειστή (η πρώτη = η τελευταία).
    """
    return [
        [center_lng - dlng, center_lat - dlat],
        [center_lng + dlng, center_lat - dlat],
        [center_lng + dlng, center_lat + dlat],
        [center_lng - dlng, center_lat + dlat],
        [center_lng - dlng, center_lat - dlat],
    ]


def _make_floor_geojson(
    venue_key: str,
    venue_lat: float,
    venue_lng: float,
    floor_number: int,
    booths_rows: int = 6,
    booths_cols: int = 5,
):
    """Φτιάχνει GeoJSON FeatureCollection με:
    - ένα "κτήριο" (μεγάλο ορθογώνιο)
    - ένα grid από booths
    - μερικά rooms

    Όλα είναι πολύ απλά, μόνο για να δοκιμάσουμε tap/highlight/floors.
    """

    # Μεγάλο ορθογώνιο που παριστάνει το "κτήριο"
    building = {
        "type": "Feature",
        "id": f"building_{venue_key}_F{floor_number}",
        "properties": {"type": "building", "floor": floor_number},
        "geometry": {
            "type": "Polygon",
            "coordinates": [_rectangle(venue_lat, venue_lng, 0.00035, 0.00045)],
        },
    }

    features = [building]

    # Ζώνη για booths (λίγο πιο μέσα)
    base_lat = venue_lat
    base_lng = venue_lng

    # Μέγεθος "κελιού" grid
    cell_dlat = 0.00008
    cell_dlng = 0.00009

    start_lat = base_lat - (booths_rows / 2) * cell_dlat
    start_lng = base_lng - (booths_cols / 2) * cell_dlng

    booth_features = []
    room_features = []

    booth_index = 1
    for r in range(booths_rows):
        for c in range(booths_cols):
            clat = start_lat + r * cell_dlat
            clng = start_lng + c * cell_dlng

            booth_code = f"B{booth_index:03d}"
            feature_id = f"booth_{venue_key}_F{floor_number}_{booth_code}"

            booth = {
                "type": "Feature",
                "id": feature_id,
                "properties": {
                    "type": "booth",
                    "floor": floor_number,
                    "code": booth_code,
                    "name": f"Dummy Booth {booth_code}",
                    # Για το μέλλον: tags/topics
                    "topics": [],
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [_rectangle(clat, clng, 0.00003, 0.000035)],
                },
            }
            booth_features.append(booth)
            booth_index += 1

    # 3 Rooms σε κάθε floor, σε άλλο σημείο
    for i in range(1, 4):
        room_code = f"R{i:02d}"
        clat = base_lat + 0.00022 - i * 0.00008
        clng = base_lng + 0.00030
        feature_id = f"room_{venue_key}_F{floor_number}_{room_code}"

        room = {
            "type": "Feature",
            "id": feature_id,
            "properties": {
                "type": "room",
                "floor": floor_number,
                "code": room_code,
                "name": f"Room {room_code}",
                "topics": [],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [_rectangle(clat, clng, 0.00005, 0.00006)],
            },
        }
        room_features.append(room)

    features.extend(booth_features)
    features.extend(room_features)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def seed():
    """Seed venues, floors, and map features into the database."""
    db: Session = SessionLocal()
    try:
        existing = db.execute(select(Venue)).scalars().first()
        if existing:
            print("Υπάρχουν ήδη venues στη βάση. Δεν ξανακάνω seed.")
            return

        # ΠΡΟΣΟΧΗ: Οι συντεταγμένες εδώ είναι για DUMMY χρήση.
        # Αν θέλεις απόλυτη ακρίβεια, τις κλειδώνουμε αργότερα μία-μία.
        venues = [
            ("epidaurus", "Αρχαίο Θέατρο Επιδαύρου", 37.5960, 23.0790),
            ("acropolis_area", "Ακρόπολη / Κέντρο Αθήνας", 37.9708, 23.7261),
            ("odeon_herodes", "Ωδείο Ηρώδου Αττικού", 37.9708, 23.7244),
            ("athens_conservatoire", "Ωδείο Αθηνών", 37.9760, 23.7430),
            ("national_gallery", "Εθνική Πινακοθήκη", 37.9720, 23.7428),
            ("maria_callas_museum", "Μουσείο Μαρία Κάλλας", 37.9756, 23.7330),
            ("cine_paris", "Cine Paris", 37.9720, 23.7309),
            ("french_institute", "Γαλλικό Ινστιτούτο", 37.9830, 23.7325),
            ("piraeus_tower", "Piraeus Tower", 37.9447, 23.6439),
        ]

        venue_rows = []
        for key, name, lat, lng in venues:
            v = Venue(key=key, name=name, lat=lat, lng=lng, default_zoom=16.0, has_indoor=True)
            db.add(v)
            venue_rows.append(v)

        db.commit()

        # Πρέπει να κάνουμε refresh για να πάρουμε τα ids
        for v in venue_rows:
            db.refresh(v)

        print(f"✅ Δημιουργήθηκαν {len(venue_rows)} venues.")

        # Floors + GeoJSON + MapFeatures
        for v in venue_rows:
            # Dummy: 3 floors για όλα τα venues
            for floor in [0, 1, 2]:
                geo = _make_floor_geojson(v.key, v.lat, v.lng, floor)
                vf = VenueFloor(venue_id=v.id, floor_number=floor, geojson=geo)
                db.add(vf)

                # Δημιουργούμε αντίστοιχα map_features για booths/rooms
                for feat in geo["features"]:
                    ftype = feat["properties"].get("type")
                    if ftype not in ("booth", "room"):
                        continue

                    feature_key = str(feat["id"])  # ίδιο id με το geojson
                    code = feat["properties"].get("code", "")
                    fname = feat["properties"].get("name", "")

                    # Υπολογίζουμε centroid ως "μέσο" (για dummy: παίρνουμε το πρώτο point και προσθέτουμε μικρή μετατόπιση)
                    # Για σωστό centroid θα το βελτιώσουμε αργότερα.
                    coords = feat["geometry"]["coordinates"][0]
                    # coords: [[lng,lat], ...]
                    lngs = [p[0] for p in coords]
                    lats = [p[1] for p in coords]
                    centroid_lng = sum(lngs) / len(lngs)
                    centroid_lat = sum(lats) / len(lats)

                    mf = MapFeature(
                        venue_id=v.id,
                        floor_number=floor,
                        feature_key=feature_key,
                        feature_type=ftype,
                        code=code,
                        name=fname,
                        centroid_lat=centroid_lat,
                        centroid_lng=centroid_lng,
                    )
                    db.add(mf)

        db.commit()
        print(f"✅ Δημιουργήθηκαν floors και map features για όλα τα venues.")

        # -----------------------------
        # DUMMY ΧΡΗΣΤΕΣ / GROUPS / ΜΗΝΥΜΑΤΑ
        # (για να δοκιμάζεις Groups & DM αμέσως)
        # -----------------------------
        from app.models.user import User
        from app.models.group import Group
        from app.core.security import hash_password
        from app.core.enums import UserRole

        # Αν υπάρχουν ήδη χρήστες, δεν ξανασπέρνουμε.
        existing_user = db.execute(select(User).limit(1)).scalar_one_or_none()
        if existing_user is None:
            u = User(email="a@a.a", password_hash="a", full_name="a", role=UserRole.attendee)
            u1 = User(email="alice@example.com", password_hash="dummy_hash", full_name="Alice", role=UserRole.attendee)
            u2 = User(email="bob@example.com", password_hash="dummy_hash", full_name="Bob", role=UserRole.attendee)
            u3 = User(email="exhibitor@example.com", password_hash="dummy_hash", full_name="Exhibitor Demo", role=UserRole.exhibitor)
            db.add_all([u, u1, u2, u3])
            db.commit()
            print("✅ Δημιουργήθηκαν 3 dummy χρήστες.")
        else:
            print("ℹ️  Οι χρήστες υπάρχουν ήδη, παράλειψη.")

        # Groups: με ref_key ώστε αργότερα να τα δένουμε με Topics/Exhibitors/Sessions κλπ
        existing_group = db.execute(select(Group).limit(1)).scalar_one_or_none()
        if existing_group is None:
            groups = [
                Group(group_type="topic", ref_key="topic:ai-deeptech", title="AI & DeepTech", description="Ομάδα για AI & DeepTech"),
                Group(group_type="venue", ref_key="venue:epidaurus", title="Επίδαυρος", description="Ομάδα για το venue της Επιδαύρου"),
                Group(group_type="venue", ref_key="venue:piraeus_tower", title="Piraeus Tower", description="Ομάδα για το venue του Πύργου Πειραιά"),
                Group(group_type="interest", ref_key="interest:fintech", title="Fintech", description="Ομάδα για όσους ενδιαφέρονται για Fintech"),
            ]
            db.add_all(groups)
            db.commit()
            print("✅ Δημιουργήθηκαν 4 dummy groups.")
        else:
            print("ℹ️  Τα groups υπάρχουν ήδη, παράλειψη.")

        print("\n🎉 Seed ολοκληρώθηκε επιτυχώς! 🎉")

    finally:
        db.close()


run = seed

if __name__ == "__main__":
    run()
