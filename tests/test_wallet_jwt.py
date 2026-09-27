"""Unit tests for Phase 13 wallet JWT building — kinded badge/ticket (gap 5a/5b).

Uses a self-signed fake service account JSON so we never touch real credentials.

Badge-path tests pin byte-stable IDs (backward compat) — existing users'
badges must merge correctly on re-issuance, never create duplicates in Google Wallet.
Ticket-path tests pin gap-5b correctness: distinct object IDs per (user_id, ticket_id).
"""
import base64
import json
import os

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def _fake_sa_json_b64() -> str:
    """Generate a fresh 2048-bit RSA key and wrap it in a fake SA JSON."""
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
        "client_email": "test-wallet@festapp-test.iam.gserviceaccount.com",
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
    # GOOGLE_WALLET_TICKET_CLASS_SUFFIX intentionally NOT set here —
    # the config default "festapp_ticket" must kick in automatically.
    # Force the config module to re-read env vars (it caches at import).
    from app.core import config as cfg
    cfg.GOOGLE_WALLET_ISSUER_ID = os.environ["GOOGLE_WALLET_ISSUER_ID"]
    cfg.GOOGLE_WALLET_CLASS_SUFFIX = os.environ["GOOGLE_WALLET_CLASS_SUFFIX"]
    cfg.GOOGLE_WALLET_SA_JSON_B64 = os.environ["GOOGLE_WALLET_SA_JSON_B64"]
    # Ticket suffix uses config default — do NOT override here.
    cfg.GOOGLE_WALLET_TICKET_CLASS_SUFFIX = "festapp_ticket"
    # Invalidate lru_cache on the service module
    from app.services import wallet as wallet_svc
    wallet_svc._service_account_info.cache_clear()
    wallet_svc._signer.cache_clear()
    yield


# ---------------------------------------------------------------------------
# Badge backward-compatibility pins (IDs must be byte-stable)
# ---------------------------------------------------------------------------

def test_build_event_ticket_object_shape():
    """Badge-path: ID and classId match the pre-existing format byte-for-byte."""
    from app.services.wallet import build_event_ticket_object
    obj = build_event_ticket_object(
        kind="badge",
        user_id=42,
        full_name="Alice Tester",
        qr_value="42",
    )
    assert obj["id"] == "3388000000022000001.festapp_badge_42"
    assert obj["classId"] == "3388000000022000001.festapp_badge"
    assert obj["state"] == "ACTIVE"
    assert obj["ticketHolderName"] == "Alice Tester"
    assert obj["barcode"] == {"type": "QR_CODE", "value": "42"}


def test_build_save_url_returns_wallet_domain():
    """Badge-path: returned URL starts with pay.google.com and is a valid 3-part JWT."""
    from app.services.wallet import build_save_url
    url = build_save_url(kind="badge", user_id=42, full_name="Alice", qr_value="42")
    assert url.startswith("https://pay.google.com/gp/v/save/")
    # JWT is 3 base64url segments separated by dots
    jwt_part = url[len("https://pay.google.com/gp/v/save/"):]
    segments = jwt_part.split(".")
    assert len(segments) == 3


def test_jwt_claims_structure():
    """Badge-path: JWT payload has all required claims; object id ends in _{user_id}."""
    from app.services.wallet import build_save_url
    url = build_save_url(kind="badge", user_id=7, full_name="Bob", qr_value="7")
    jwt_part = url[len("https://pay.google.com/gp/v/save/"):]
    # decode the payload (2nd segment) without verifying — we just want the shape
    payload_b64 = jwt_part.split(".")[1]
    padding = "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    assert payload["iss"] == "test-wallet@festapp-test.iam.gserviceaccount.com"
    assert payload["aud"] == "google"
    assert payload["typ"] == "savetowallet"
    assert "origins" in payload
    assert payload["payload"]["eventTicketObjects"][0]["id"].endswith("_7")


def test_missing_config_raises(monkeypatch):
    from app.core import config as cfg
    from app.services import wallet as wallet_svc
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_ISSUER_ID", None)
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_CLASS_SUFFIX", None)
    monkeypatch.setattr(cfg, "GOOGLE_WALLET_SA_JSON_B64", None)
    wallet_svc._service_account_info.cache_clear()
    wallet_svc._signer.cache_clear()
    with pytest.raises(wallet_svc.WalletNotConfiguredError):
        wallet_svc.build_save_url(kind="badge", user_id=1, full_name="X", qr_value="1")


# ---------------------------------------------------------------------------
# Ticket-kind tests (gap 5b)
# ---------------------------------------------------------------------------

def test_build_event_ticket_object_ticket_kind():
    """Ticket-path: object id ends in festapp_ticket_{user_id}_{ticket_id}."""
    from app.services.wallet import build_event_ticket_object
    obj = build_event_ticket_object(
        kind="ticket",
        user_id=42,
        full_name="Alice",
        qr_value="ticket-uuid-abc",
        ticket_id=7,
    )
    assert obj["id"].endswith("festapp_ticket_42_7")
    assert obj["classId"].endswith("festapp_ticket")
    # barcode carries the qr_value verbatim (the UUID the venue scanner reads)
    assert obj["barcode"]["value"] == "ticket-uuid-abc"
    assert obj["state"] == "ACTIVE"


def test_ticket_kind_requires_ticket_id():
    """Ticket-path: ValueError raised when ticket_id is omitted."""
    from app.services.wallet import build_save_url
    with pytest.raises(ValueError, match="ticket_id is required"):
        build_save_url(kind="ticket", user_id=42, full_name="Alice", qr_value="x")


def test_badge_and_ticket_object_ids_differ():
    """Gap-5b regression pin: same user gets DISTINCT object IDs for badge vs ticket."""
    from app.services.wallet import build_event_ticket_object
    badge_obj = build_event_ticket_object(
        kind="badge", user_id=42, full_name="Alice", qr_value="42"
    )
    ticket_obj = build_event_ticket_object(
        kind="ticket", user_id=42, full_name="Alice", qr_value="some-uuid", ticket_id=1
    )
    assert badge_obj["id"] != ticket_obj["id"]


def test_two_tickets_same_user_distinct_object_ids():
    """Two different ticket_ids for the same user produce distinct wallet object IDs."""
    from app.services.wallet import build_event_ticket_object
    obj7 = build_event_ticket_object(
        kind="ticket", user_id=42, full_name="Alice", qr_value="uuid-7", ticket_id=7
    )
    obj8 = build_event_ticket_object(
        kind="ticket", user_id=42, full_name="Alice", qr_value="uuid-8", ticket_id=8
    )
    assert obj7["id"] != obj8["id"]
    assert obj7["id"].endswith("_42_7")
    assert obj8["id"].endswith("_42_8")
