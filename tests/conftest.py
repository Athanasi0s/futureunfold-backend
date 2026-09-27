"""Pytest scaffold for festapp-backend Phase 13 tests.

In-memory SQLite session + FastAPI TestClient + fabricated admin user.
"""
import os
import sys
from pathlib import Path

# Ensure the backend package is importable regardless of CWD.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# SQLite URL must be set BEFORE importing any app module that reads DATABASE_URL at import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-phase13")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Monkey-patch feature-flag resolver BEFORE importing `app.main` so the notifications
# router's `require_feature("notifications")` dep doesn't try to query the app_config
# table (which uses JSONB — SQLite can't compile that column type). Returning the
# FEATURE_REGISTRY defaults all-True keeps every flag enabled in tests.
from app.core import feature_flags as _feature_flags

def _all_on_flags(_db=None):  # noqa: ANN001 — dialect-agnostic test shim
    return {key: True for key in _feature_flags.FEATURE_REGISTRY}

_feature_flags.get_merged_flags = _all_on_flags

from app.main import app
from app.db.base import Base
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.push_token import PushToken
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.user_agenda import UserAgenda
from app.models.session import Session as ProgramSession
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.app_config import AppConfig
from app.models.eventora_magic_link_redemption import EventoraMagicLinkRedemption
from app.core.enums import UserRole


# Phase 13 Plan 05 — Some columns use PostgreSQL-specific types (ARRAY, JSONB) that
# SQLite cannot compile. Swap to SQLite-friendly variants BEFORE
# Base.metadata.create_all() fires so the column still exists.
import sqlalchemy as _sa


def _sqlite_safe(table, col_name: str, replacement) -> None:
    col = table.columns.get(col_name)
    if col is None:
        return
    if getattr(col.type, "_test_safe", False):
        return
    col.type = replacement
    col.type._test_safe = True  # type: ignore[attr-defined] — idempotency marker


_sqlite_safe(ProgramSession.__table__, "topic_tags", _sa.String())
_sqlite_safe(AuditLog.__table__, "detail", _sa.JSON())
_sqlite_safe(AppConfig.__table__, "value", _sa.JSON())


# Whitelist of tables created on the SQLite test engine. Production models include
# PostgreSQL-specific types (JSONB, geometry) that SQLite cannot compile; we only
# need the subset our tests actually hit. Future Phase 13 test files can extend this
# list OR override the `test_engine` fixture with their own subset.
_TEST_TABLES = (
    User.__table__,
    PushToken.__table__,
    Group.__table__,
    GroupMember.__table__,
    GroupMessage.__table__,
    UserAgenda.__table__,
    ProgramSession.__table__,
    AuditLog.__table__,
    Notification.__table__,
    AppConfig.__table__,
    EventoraMagicLinkRedemption.__table__,
)


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=list(_TEST_TABLES))
    yield engine
    Base.metadata.drop_all(bind=engine, tables=list(_TEST_TABLES))
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def test_user(db_session):
    user = User(
        id=1,
        email="test@example.com",
        password_hash="x",
        full_name="Test User",
        role=UserRole.attendee,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(db_session, test_user):
    def _get_db_override():
        yield db_session
    def _get_current_user_override():
        return test_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_current_user_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
