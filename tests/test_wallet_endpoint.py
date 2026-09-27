"""End-to-end tests for POST /me/wallet/pass/{kind} using TestClient + fabricated credentials.

Phase 13 gap 5b:
- Badge path: backward-compatible POST /me/wallet/pass/badge + legacy /me/wallet/pass
- Ticket path: POST /me/wallet/pass/ticket with ownership check, qr_code-as-barcode pin
- Cross-user forgery: 404 when ticket belongs to a different user (T-13-GAP-10-01)
"""
import base64
import json
import os
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import sqlalchemy as _sa


def _fake_sa_json_b64() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    sa = {
        "type": "service_account",
        "private_key_id": "fakekeyid",
        "private_key": pem,
        "client_email": "test@festapp-test.iam.gserviceaccount.com",
        "client_id": "0",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://example.com",
    }
    return base64.b64encode(json.dumps(sa).encode()).decode()


@pytest.fixture(autouse=True)
def _wallet_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_WALLET_ISSUER_ID", "3388000000022000001")
    monkeypatch.setenv("GOOGLE_WALLET_CLASS_SUFFIX", "festapp_badge")
    monkeypatch.setenv("GOOGLE_WALLET_SA_JSON_B64", _fake_sa_json_b64())
    from app.core import config as cfg
    cfg.GOOGLE_WALLET_ISSUER_ID = os.environ["GOOGLE_WALLET_ISSUER_ID"]
    cfg.GOOGLE_WALLET_CLASS_SUFFIX = os.environ["GOOGLE_WALLET_CLASS_SUFFIX"]
    cfg.GOOGLE_WALLET_SA_JSON_B64 = os.environ["GOOGLE_WALLET_SA_JSON_B64"]
    cfg.GOOGLE_WALLET_TICKET_CLASS_SUFFIX = "festapp_ticket"
    from app.services import wallet as wallet_svc
    wallet_svc._service_account_info.cache_clear()
    wallet_svc._signer.cache_clear()
    yield


def _decode_jwt_payload(save_url: str) -> dict:
    """Decode JWT payload from a save_url without verifying signature."""
    jwt_part = save_url[len("https://pay.google.com/gp/v/save/"):]
    payload_b64 = jwt_part.split(".")[1]
    padding = "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))


def _seed_ticket(db_session, user_id: int, qr_code: str | None = None):
    """Insert a minimal TicketPackage + Ticket for the given user_id.

    Returns the Ticket ORM instance (id + qr_code populated after flush).
    Uses a random UUID for qr_code if not supplied.
    """
    from app.models.ticket_package import TicketPackage
    from app.models.ticket import Ticket, TicketStatus

    qr = qr_code or str(uuid.uuid4())
    pkg = TicketPackage(
        ref_key=f"pkg_{qr[:8]}",
        name="Festival Pass",
        price_eur=50,
        stripe_price_id="price_test_123",
        features=[],
    )
    db_session.add(pkg)
    db_session.flush()

    ticket = Ticket(
        user_id=user_id,
        package_id=pkg.id,
        stripe_payment_intent_id=f"pi_{qr[:16]}",
        qr_code=qr,
        status=TicketStatus.active,
    )
    db_session.add(ticket)
    db_session.flush()
    return ticket


# ---------------------------------------------------------------------------
# conftest extension: make Ticket and TicketPackage tables available in SQLite
# ---------------------------------------------------------------------------

# Note: these patches must happen BEFORE the test engine creates tables.
# We piggy-back on the conftest _TEST_TABLES and _sqlite_safe mechanics by
# doing the patching here at module import time.
from app.models.ticket_package import TicketPackage as _TicketPackage
from app.models.ticket import Ticket as _Ticket
from tests.conftest import _sqlite_safe, _TEST_TABLES

# TicketPackage.features is JSONB — swap to JSON for SQLite
_sqlite_safe(_TicketPackage.__table__, "features", _sa.JSON())

# Ticket.status uses PostgreSQL native enum — swap to String for SQLite
_col_status = _Ticket.__table__.columns.get("status")
if _col_status is not None and not getattr(_col_status.type, "_test_safe", False):
    _col_status.type = _sa.String()
    _col_status.type._test_safe = True


# Extend the whitelist so test_engine creates Ticket + TicketPackage tables
def pytest_configure(config):
    pass


@pytest.fixture()
def test_engine_with_tickets(test_engine):
    """Extend the base test_engine to also include Ticket + TicketPackage tables."""
    from app.models.ticket_package import TicketPackage
    from app.models.ticket import Ticket
    from app.db.base import Base
    extra = [TicketPackage.__table__, Ticket.__table__]
    Base.metadata.create_all(bind=test_engine, tables=extra)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine, tables=extra)


@pytest.fixture()
def db_session_tickets(test_engine_with_tickets):
    """DB session that includes Ticket + TicketPackage tables."""
    from sqlalchemy.orm import sessionmaker
    TestingSessionLocal = sessionmaker(
        bind=test_engine_with_tickets, autoflush=False, autocommit=False
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client_with_tickets(db_session_tickets, test_user):
    """TestClient using db_session_tickets so wallet ticket endpoint can query Ticket."""
    from app.main import app
    from app.core.deps import get_db, get_current_user
    from app.core.enums import UserRole
    from app.models.user import User

    # Insert the test_user into THIS session (it was inserted in another session)
    # We recreate it here to avoid session boundary issues.
    user = User(
        id=1,
        email="test@example.com",
        password_hash="x",
        full_name="Test User",
        role=UserRole.attendee,
    )
    # merge() returns the session-tracked instance; use that one, not the original
    user = db_session_tickets.merge(user)
    db_session_tickets.commit()
    db_session_tickets.refresh(user)

    def _get_db_override():
        yield db_session_tickets

    def _get_current_user_override():
        return user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_current_user_override
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c, db_session_tickets, user
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Badge path tests (backward compat)
# ---------------------------------------------------------------------------

def test_post_wallet_pass_badge_kinded_returns_save_url(client):
    r = client.post("/me/wallet/pass/badge")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "save_url" in body
    assert body["save_url"].startswith("https://pay.google.com/gp/v/save/")


def test_post_wallet_pass_legacy_route_still_works(client, test_user):
    """Legacy POST /me/wallet/pass (no kind) still issues a badge pass."""
    r = client.post("/me/wallet/pass")
    assert r.status_code == 200, r.text
    payload = _decode_jwt_payload(r.json()["save_url"])
    obj = payload["payload"]["eventTicketObjects"][0]
    assert f"festapp_badge_{test_user.id}" in obj["id"]


def test_post_wallet_pass_uses_user_id_as_qr(client, test_user):
    r = client.post("/me/wallet/pass/badge")
    assert r.status_code == 200
    payload = _decode_jwt_payload(r.json()["save_url"])
    obj = payload["payload"]["eventTicketObjects"][0]
    assert obj["barcode"]["value"] == str(test_user.id)


# ---------------------------------------------------------------------------
# Ticket path tests (gap 5b)
# ---------------------------------------------------------------------------

def test_post_wallet_pass_ticket_returns_distinct_object_id(client_with_tickets):
    c, db, user = client_with_tickets
    ticket = _seed_ticket(db, user.id)
    db.commit()

    r_badge = c.post("/me/wallet/pass/badge")
    assert r_badge.status_code == 200
    badge_payload = _decode_jwt_payload(r_badge.json()["save_url"])
    badge_id = badge_payload["payload"]["eventTicketObjects"][0]["id"]

    r_ticket = c.post("/me/wallet/pass/ticket", json={"ticket_id": ticket.id})
    assert r_ticket.status_code == 200
    ticket_payload = _decode_jwt_payload(r_ticket.json()["save_url"])
    ticket_obj_id = ticket_payload["payload"]["eventTicketObjects"][0]["id"]

    assert badge_id != ticket_obj_id
    assert ticket_obj_id.endswith(f"_{user.id}_{ticket.id}")


def test_post_wallet_pass_ticket_barcode_uses_qr_code(client_with_tickets):
    """Gap-5b correctness pin: wallet pass barcode == Ticket.qr_code (UUID), NOT str(ticket_id)."""
    c, db, user = client_with_tickets
    known_qr = "wallet-test-uuid-12345"
    ticket = _seed_ticket(db, user.id, qr_code=known_qr)
    db.commit()

    r = c.post("/me/wallet/pass/ticket", json={"ticket_id": ticket.id})
    assert r.status_code == 200, r.text
    payload = _decode_jwt_payload(r.json()["save_url"])
    barcode_value = payload["payload"]["eventTicketObjects"][0]["barcode"]["value"]

    # Must equal the UUID string (what the venue scanner reads), NOT str(ticket_id)
    assert barcode_value == known_qr
    assert barcode_value != str(ticket.id)


def test_post_wallet_pass_ticket_requires_ticket_id(client_with_tickets):
    c, db, user = client_with_tickets
    r = c.post("/me/wallet/pass/ticket", json={})
    assert r.status_code == 400, r.text
    assert "ticket_id" in r.json()["detail"].lower() or "required" in r.json()["detail"].lower()


def test_post_wallet_pass_ticket_404_when_not_owned(client_with_tickets):
    """T-13-GAP-10-01: cross-user pass forgery returns 404 (identical to not-found)."""
    c, db, user = client_with_tickets
    from app.models.user import User
    from app.core.enums import UserRole

    other_user = User(
        id=99,
        email="other@example.com",
        password_hash="x",
        full_name="Other User",
        role=UserRole.attendee,
    )
    db.add(other_user)
    db.flush()

    other_ticket = _seed_ticket(db, other_user.id)
    db.commit()

    # Authenticated as user (id=1), trying to get pass for other_user's ticket
    r = c.post("/me/wallet/pass/ticket", json={"ticket_id": other_ticket.id})
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Ticket not found"


def test_post_wallet_pass_ticket_404_when_not_exists(client_with_tickets):
    """Non-existent ticket_id returns 404 with identical message (no info leak)."""
    c, db, user = client_with_tickets
    r = c.post("/me/wallet/pass/ticket", json={"ticket_id": 999999})
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Ticket not found"


def test_post_wallet_pass_invalid_kind_returns_422(client):
    r = client.post("/me/wallet/pass/badgess")
    assert r.status_code == 422


def test_post_wallet_pass_trailing_slash_behavior(client):
    """Pin FastAPI routing: trailing slash → 307/422; legacy no-slash → 200."""
    r_slash = client.post("/me/wallet/pass/", follow_redirects=False)
    assert r_slash.status_code in (307, 422), f"Expected 307 or 422, got {r_slash.status_code}"

    r_legacy = client.post("/me/wallet/pass")
    assert r_legacy.status_code == 200, f"Expected 200 (legacy), got {r_legacy.status_code}"


def test_post_wallet_pass_503_when_not_configured(client, monkeypatch):
    from app.core import config as cfg
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_ISSUER_ID", None)
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_CLASS_SUFFIX", None)
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_SA_JSON_B64", None)
    from app.services import wallet as wallet_svc
    wallet_svc._service_account_info.cache_clear()
    wallet_svc._signer.cache_clear()
    r = client.post("/me/wallet/pass/badge")
    assert r.status_code == 503
    assert "GOOGLE_WALLET_SA_JSON_B64" in r.json()["detail"]
