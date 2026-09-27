"""Seed outdoor map venues with polygon geometry stored as JSONB.

Adapted from the panathinaia demo with richer descriptions and tighter layout.
Idempotent: deletes existing venues with geojson_geometry and re-seeds.

Run with:
    python -m app.seed.seed_outdoor_map
"""

from __future__ import annotations

from sqlalchemy import select, delete

from app.db.session import SessionLocal
from app.models.venue import Venue


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def make_rect(cx: float, cy: float, w: float, h: float) -> dict:
    """Create a GeoJSON Polygon dict (lng, lat) around center point."""
    half_w, half_h = w / 2, h / 2
    return {
        "type": "Polygon",
        "coordinates": [[
            [cx - half_w, cy - half_h],
            [cx + half_w, cy - half_h],
            [cx + half_w, cy + half_h],
            [cx - half_w, cy + half_h],
            [cx - half_w, cy - half_h],
        ]],
    }


CATEGORY_COLORS = {
    "exhibitor": "CC8833",
    "stage": "CC4466",
    "amenity": "3355CC",
    "sponsor": "66AACC",
}


def avatar_url(name: str, category: str) -> str:
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    bg = CATEGORY_COLORS.get(category, "888888")
    return f"https://ui-avatars.com/api/?name={initials}&background={bg}&color=fff&size=128"


# ---------------------------------------------------------------------------
# Athens center
# ---------------------------------------------------------------------------

CENTER_LAT = 37.9755
CENTER_LNG = 23.7257

# Booth dimensions (much smaller than before — matches panathinaia demo)
BOOTH_W = 0.00008   # ~6m wide
BOOTH_H = 0.00006   # ~7m tall

# ---------------------------------------------------------------------------
# Exhibitor definitions (from panathinaia with rich descriptions)
# ---------------------------------------------------------------------------

EXHIBITORS = [
    ("GreenTech Solutions", "Sustainable energy solutions and smart grid technology for urban environments"),
    ("Delphi Robotics", "Autonomous robotics systems for industrial automation and precision manufacturing"),
    ("Sparta Payments", "Next-generation payment processing with blockchain-backed settlement"),
    ("Syros Analytics", "AI-powered business intelligence and predictive analytics platform"),
    ("Samos Healthtech", "Wearable health monitoring devices with real-time diagnostics"),
    ("Lesbos Edtech", "Interactive learning platforms using AR and gamification for K-12 education"),
    ("Komotini Green", "Biodegradable packaging and circular economy solutions for retail"),
    ("Kastoria Textiles", "Smart textiles with embedded sensors for athletic performance tracking"),
    ("Ioannina Med", "AI-assisted medical imaging and diagnostic decision support systems"),
    ("Xanthi Nanotech", "Nanomaterial coatings for industrial corrosion prevention and energy efficiency"),
    ("Corfu Blockchain", "Decentralized identity verification and secure document management"),
    ("Olympus Cyber", "Enterprise cybersecurity platform with zero-trust architecture"),
    ("Attica Labs", "Quantum-resistant encryption algorithms for enterprise communications"),
    ("Mykonos VR", "Immersive virtual reality experiences for tourism and cultural heritage"),
    ("Naxos Energy", "Solar microgrids and community energy storage solutions"),
    ("Volos Space", "Satellite data analytics for precision agriculture and environmental monitoring"),
    ("Larissa 3D", "Industrial 3D printing services for aerospace and automotive components"),
    ("Hydra Security", "AI-driven surveillance and smart city safety management systems"),
    ("Chios Logistics", "Supply chain optimization using IoT sensors and predictive routing"),
    ("Tripoli Climate", "Carbon footprint tracking and offset marketplace for businesses"),
    ("Nafplio Audio", "Spatial audio technology for immersive entertainment and conferencing"),
    ("Rhodes SaaS", "Multi-tenant SaaS platform builder with automated DevOps pipeline"),
    ("Milos Quantum", "Quantum computing simulation tools for pharmaceutical research"),
    ("Thessaloniki Dev", "Low-code development platform for enterprise application modernization"),
    ("Zakynthos AR", "Augmented reality navigation and indoor wayfinding solutions"),
    ("Korres Digital", "Digital beauty and wellness platform with AI skin analysis"),
    ("Trikala Mobility", "Electric micromobility fleet management and urban transport planning"),
    ("Kalamata Agritech", "Precision agriculture drones and crop health monitoring systems"),
    ("Drama Optics", "Advanced optical sensors for autonomous vehicle LiDAR systems"),
    ("Argos Sensors", "Industrial IoT sensor networks for predictive maintenance"),
]

COMPANY_SUFFIXES = ["Ltd", "Inc", "S.A."]

# ---------------------------------------------------------------------------
# Stages (center of venue, larger polygons)
# ---------------------------------------------------------------------------

STAGES = [
    ("Parthenon Main Stage", "The premier stage for keynotes and headline presentations"),
    ("Startup Pit", "Fast-paced startup pitches and investor matchmaking sessions"),
    ("Workshop Hall A", "Hands-on technical workshops and coding sessions"),
    ("Workshop Hall B", "Industry panels and roundtable discussions"),
]

STAGE_POSITIONS = [
    (CENTER_LNG - 0.0002, CENTER_LAT + 0.0001, 0.0003, 0.0002),
    (CENTER_LNG + 0.0002, CENTER_LAT + 0.0001, 0.0002, 0.00015),
    (CENTER_LNG - 0.0002, CENTER_LAT - 0.0004, 0.0002, 0.00015),
    (CENTER_LNG + 0.0002, CENTER_LAT - 0.0004, 0.0002, 0.00015),
]

# ---------------------------------------------------------------------------
# Amenities (edges of venue)
# ---------------------------------------------------------------------------

AMENITIES = [
    ("Food Court", "International cuisine and refreshment area"),
    ("Info Desk", "Event information, maps, and attendee support"),
    ("VIP Lounge", "Exclusive networking space for VIP badge holders"),
]

AMENITY_POSITIONS = [
    (CENTER_LNG, CENTER_LAT + 0.0005, 0.0002, 0.00015),
    (CENTER_LNG - 0.0004, CENTER_LAT - 0.0006, 0.00012, 0.0001),
    (CENTER_LNG + 0.0004, CENTER_LAT - 0.0006, 0.00015, 0.00012),
]

# ---------------------------------------------------------------------------
# Sponsor
# ---------------------------------------------------------------------------

SPONSOR = ("AI Avenue Pavilion", "Premier sponsor showcase featuring live AI demonstrations", "AI Avenue Corp")
SPONSOR_POS = (CENTER_LNG + 0.0004, CENTER_LAT - 0.0001, 0.00025, 0.0002)


# ---------------------------------------------------------------------------
# Exhibitor row layout (matching panathinaia demo — 4 rows, tight spacing)
# ---------------------------------------------------------------------------

ROW_CONFIGS = [
    ("A", CENTER_LAT + 0.00035, 8),
    ("B", CENTER_LAT + 0.00025, 8),
    ("C", CENTER_LAT - 0.00015, 7),
    ("D", CENTER_LAT - 0.00025, 7),
]

COL_SPACING = 0.00012


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def seed():
    db = SessionLocal()
    try:
        # Delete existing outdoor map venues to allow re-seeding
        db.execute(
            delete(Venue).where(Venue.geojson_geometry.isnot(None))
        )
        db.commit()

        venues = []
        sort_order = 0

        # -- Stages --
        for (name, desc), (lng, lat, w, h) in zip(STAGES, STAGE_POSITIONS):
            v = Venue(
                key=f"stage_{name.lower().replace(' ', '_')}",
                name=name,
                lat=lat,
                lng=lng,
                default_zoom=17.0,
                has_indoor=False,
                category="stage",
                description=desc,
                avatar_url=avatar_url(name, "stage"),
                company=None,
                booth_number=None,
                extrusion_height=10,
                sort_order=sort_order,
                is_active=True,
                geojson_geometry=make_rect(lng, lat, w, h),
            )
            venues.append(v)
            sort_order += 1

        # -- Exhibitors in rows --
        exhibitor_idx = 0
        for row_letter, row_lat, count in ROW_CONFIGS:
            row_start_lng = CENTER_LNG - (count * COL_SPACING) / 2
            for col in range(count):
                if exhibitor_idx >= len(EXHIBITORS):
                    break
                name, desc = EXHIBITORS[exhibitor_idx]
                booth_num = f"{row_letter}-{col + 1:02d}"
                lng = row_start_lng + col * COL_SPACING
                suffix = COMPANY_SUFFIXES[exhibitor_idx % 3]
                v = Venue(
                    key=f"exhibitor_{name.lower().replace(' ', '_')}",
                    name=name,
                    lat=row_lat,
                    lng=lng,
                    default_zoom=18.0,
                    has_indoor=False,
                    category="exhibitor",
                    description=desc,
                    avatar_url=avatar_url(name, "exhibitor"),
                    company=f"{name} {suffix}",
                    booth_number=booth_num,
                    extrusion_height=15,
                    sort_order=sort_order,
                    is_active=True,
                    geojson_geometry=make_rect(lng, row_lat, BOOTH_W, BOOTH_H),
                )
                venues.append(v)
                sort_order += 1
                exhibitor_idx += 1

        # -- Amenities --
        for (name, desc), (lng, lat, w, h) in zip(AMENITIES, AMENITY_POSITIONS):
            v = Venue(
                key=f"amenity_{name.lower().replace(' ', '_')}",
                name=name,
                lat=lat,
                lng=lng,
                default_zoom=17.0,
                has_indoor=False,
                category="amenity",
                description=desc,
                avatar_url=avatar_url(name, "amenity"),
                company=None,
                booth_number=None,
                extrusion_height=8,
                sort_order=sort_order,
                is_active=True,
                geojson_geometry=make_rect(lng, lat, w, h),
            )
            venues.append(v)
            sort_order += 1

        # -- Sponsor --
        name, desc, company = SPONSOR
        lng, lat, w, h = SPONSOR_POS
        v = Venue(
            key="sponsor_ai_avenue",
            name=name,
            lat=lat,
            lng=lng,
            default_zoom=17.0,
            has_indoor=False,
            category="sponsor",
            description=desc,
            avatar_url=avatar_url(name, "sponsor"),
            company=company,
            booth_number=None,
            extrusion_height=20,
            sort_order=sort_order,
            is_active=True,
            geojson_geometry=make_rect(lng, lat, w, h),
        )
        venues.append(v)

        db.add_all(venues)
        db.commit()

        exhibitor_count = sum(1 for v in venues if v.category == "exhibitor")
        print(f"Seeded {len(venues)} outdoor map venues.")
        print(f"  Stages:     {len(STAGES)}")
        print(f"  Exhibitors: {exhibitor_count}")
        print(f"  Amenities:  {len(AMENITIES)}")
        print(f"  Sponsors:   1")

    finally:
        db.close()


run = seed

if __name__ == "__main__":
    run()
