from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class Venue(Base):
    """Venue = ένας χώρος (pin στον outdoor χάρτη) που μπορεί να έχει floors για indoor χάρτη."""

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Σταθερό "κλειδί" για προγραμματιστική χρήση (π.χ. acropolis_area)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Όνομα που βλέπει ο χρήστης
    name: Mapped[str] = mapped_column(String(200))

    # Συντεταγμένες pin (outdoor)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    # Προτεινόμενο zoom όταν ανοίγει ο χάρτης στο venue
    default_zoom: Mapped[float] = mapped_column(Float, default=16.0)

    # Αν έχει indoor χάρτη (floors)
    has_indoor: Mapped[bool] = mapped_column(Boolean, default=True)

    # Outdoor map fields
    category: Mapped[str] = mapped_column(String(20), default="exhibitor", server_default="exhibitor")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    booth_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    extrusion_height: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    geojson_geometry: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
