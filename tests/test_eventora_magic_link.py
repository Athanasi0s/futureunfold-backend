from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.services.eventora_magic_link import (
    EventoraTokenError,
    decode_eventora_invitation,
)


SECRET = "test-secret-with-sufficient-entropy"


def _token(**overrides):
    payload = {
        "sub": "invitee-42",
        "jti": "single-use-identifier",
        "iss": "eventora",
        "aud": "future-unfold-app",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "email": "Guest@Example.com",
        "full_name": "Test Guest",
        "qr_code": "EVENTORA-QR-42",
        "invitation_id": "INV-42",
    }
    payload.update(overrides)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_decodes_valid_eventora_token():
    invitation = decode_eventora_invitation(
        _token(),
        secret=SECRET,
        issuer="eventora",
        audience="future-unfold-app",
    )
    assert invitation.email == "guest@example.com"
    assert invitation.qr_code == "EVENTORA-QR-42"


def test_rejects_expired_eventora_token():
    with pytest.raises(EventoraTokenError):
        decode_eventora_invitation(
            _token(exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
            secret=SECRET,
            issuer="eventora",
            audience="future-unfold-app",
        )


def test_rejects_missing_required_claim():
    token = _token(qr_code=None)
    with pytest.raises(EventoraTokenError):
        decode_eventora_invitation(
            token,
            secret=SECRET,
            issuer="eventora",
            audience="future-unfold-app",
        )


def test_endpoint_redeems_once_and_rejects_replay(client, monkeypatch):
    from app.api.routes import auth as auth_route

    monkeypatch.setattr(auth_route, "EVENTORA_MAGIC_LINK_SECRET", SECRET)
    monkeypatch.setattr(auth_route, "EVENTORA_MAGIC_LINK_ISSUER", "eventora")
    monkeypatch.setattr(
        auth_route, "EVENTORA_MAGIC_LINK_AUDIENCE", "future-unfold-app"
    )

    token = _token()
    first = client.post("/auth/eventora", json={"token": token})
    assert first.status_code == 200
    assert first.json()["token_type"] == "bearer"

    replay = client.post("/auth/eventora", json={"token": token})
    assert replay.status_code == 409
