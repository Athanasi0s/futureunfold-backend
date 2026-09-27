from sqlalchemy import Integer, ForeignKey, String, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class MapFeature(Base):
    """Ένα αντικείμενο στον χάρτη: booth ή room.

    Σημαντικό: το feature_key είναι το "μοναδικό όνομα" που χρησιμοποιούμε και στο κινητό για highlight.
    """

    __tablename__ = "map_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    floor_number: Mapped[int] = mapped_column(Integer, index=True)

    # π.χ. booth_acropolis_area_F1_B012
    feature_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    # booth ή room
    feature_type: Mapped[str] = mapped_column(String(32), index=True)

    # π.χ. H48-006 (προαιρετικό για dummy)
    code: Mapped[str] = mapped_column(String(64), default="")

    name: Mapped[str] = mapped_column(String(200), default="")

    # Κέντρο του polygon (για να κάνουμε zoom)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lng: Mapped[float] = mapped_column(Float)

    # Relationships
    venue = relationship("Venue", lazy="joined")
