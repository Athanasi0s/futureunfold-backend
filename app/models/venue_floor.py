from sqlalchemy import Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class VenueFloor(Base):
    """Ένας όροφος ενός venue. Κρατάει GeoJSON για booths/rooms."""

    __tablename__ = "venue_floors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    floor_number: Mapped[int] = mapped_column(Integer, index=True)

    # GeoJSON (FeatureCollection). Το κρατάμε στη βάση για το dummy layout.
    geojson: Mapped[dict] = mapped_column(JSONB)
