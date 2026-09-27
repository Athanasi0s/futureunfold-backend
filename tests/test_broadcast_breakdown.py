"""PUSH-04 — device breakdown + PUSH-01/02 template resolution integration.

Verifies that POST /admin/push/broadcast:
  - Returns total_devices / ios_count / android_count / unknown_count grouped
    by push_tokens.platform.
  - Resolves deeplink_template at send time and reflects the resolved value
    in BroadcastPushOut.resolved_deeplink.
  - Surfaces EmptyTargetError as HTTP 400 with the canonical message.
  - Rejects unknown templates with HTTP 422 (schema-level enum guard).
"""
from unittest.mock import patch

import pytest

from app.core.enums import UserRole
from app.core.deps import require_admin
from app.main import app
from app.models.user import User
from app.models.push_token import PushToken


@pytest.fixture()
def admin_client(client, db_session, test_user):
    test_user.role = UserRole.admin
    db_session.commit()
    app.dependency_overrides[require_admin] = lambda: test_user
    yield client
    app.dependency_overrides.pop(require_admin, None)


def _seed(db, email: str, platform: str | None) -> User:
    u = User(email=email, password_hash="x", full_name=email, role=UserRole.attendee)
    db.add(u)
    db.flush()
    db.add(PushToken(user_id=u.id, token=f"t-{email}", platform=platform))
    db.commit()
    return u


def test_breakdown_counts_per_platform(admin_client, db_session):
    _seed(db_session, "ios1@x", "ios")
    _seed(db_session, "ios2@x", "ios")
    _seed(db_session, "and1@x", "android")
    _seed(db_session, "legacy@x", None)
    with patch("app.api.routes.admin_push.send_push"):
        r = admin_client.post("/admin/push/broadcast", json={"title": "t", "body": "b"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_devices"] == 4
    assert body["ios_count"] == 2
    assert body["android_count"] == 1
    assert body["unknown_count"] == 1


def test_template_none_resolves_to_null_deeplink(admin_client, db_session):
    _seed(db_session, "u@x", "ios")
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "t", "body": "b", "deeplink_template": "none"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["resolved_deeplink"] is None
    # send_push received deeplink=None
    assert mock_send.call_args.kwargs["deeplink"] is None


def test_empty_trending_group_returns_400(admin_client, db_session):
    _seed(db_session, "u@x", "ios")
    # No GroupMember rows → resolver raises EmptyTargetError → 400.
    r = admin_client.post(
        "/admin/push/broadcast",
        json={"title": "t", "body": "b", "deeplink_template": "trending_group"},
    )
    assert r.status_code == 400
    assert "trending group" in r.json()["detail"].lower()


def test_unknown_template_rejected_by_schema(admin_client):
    r = admin_client.post(
        "/admin/push/broadcast",
        json={"title": "t", "body": "b", "deeplink_template": "evil_path"},
    )
    assert r.status_code == 422
