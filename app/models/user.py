from sqlalchemy import Boolean, Column, Integer, String, DateTime, Date, func, text
from sqlalchemy.types import Enum as SQLEnum

# ✅ ΣΤΟ PROJECT ΣΟΥ ΤΟ BASE ΕΙΝΑΙ ΣΤΟ app/db/base.py
from app.db.base import Base
from app.core.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)

    # ✅ role as Enum with default
    role = Column(SQLEnum(UserRole, name="user_roles", native_enum=True), nullable=False, server_default=text("'attendee'"))

    linkedin_url = Column(String, nullable=True)  # LinkedIn profile URL
    avatar_url = Column(String, nullable=True)  # URL to avatar image
    cover_url = Column(String, nullable=True)  # URL to cover/banner image
    
    bio = Column(String, nullable=True)
    company = Column(String, nullable=True)

    # External admission identity supplied by EVENTORA. These fields are
    # tenant-local and must never be exposed through public user endpoints.
    eventora_invitation_id = Column(String, unique=True, index=True, nullable=True)
    eventora_qr_code = Column(String, unique=True, index=True, nullable=True)

    theme_preference = Column(String, nullable=True, default=None)

    # Demographics (Phase 9 - STAT-02, STAT-03)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(30), nullable=True)  # "male", "female", "prefer_not_to_say"

    is_blocked = Column(Boolean, nullable=False, server_default=text("false"), default=False)

    # Points system (QR scans use the user id directly)
    points = Column(Integer, nullable=False, server_default=text("0"), default=0)

    # JWT invalidation counter — bumped on every role change (Phase 11)
    token_version = Column(Integer, nullable=False, server_default=text("0"), default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


