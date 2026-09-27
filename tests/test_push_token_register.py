"""PUSH-04 round-trip: register with platform + verify breakdown-ready storage."""
from sqlalchemy import select

from app.models.push_token import PushToken


def test_register_without_platform_defaults_to_null(client, db_session, test_user):
    r = client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[legacy]"},
    )
    assert r.status_code == 204
    row = db_session.execute(
        select(PushToken).where(PushToken.token == "ExponentPushToken[legacy]")
    ).scalar_one()
    assert row.platform is None
    assert row.user_id == test_user.id


def test_register_with_android_platform_persists(client, db_session, test_user):
    r = client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[android1]", "platform": "android"},
    )
    assert r.status_code == 204
    row = db_session.execute(
        select(PushToken).where(PushToken.token == "ExponentPushToken[android1]")
    ).scalar_one()
    assert row.platform == "android"


def test_register_with_ios_platform_persists(client, db_session, test_user):
    r = client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[ios1]", "platform": "ios"},
    )
    assert r.status_code == 204
    row = db_session.execute(
        select(PushToken).where(PushToken.token == "ExponentPushToken[ios1]")
    ).scalar_one()
    assert row.platform == "ios"


def test_register_with_invalid_platform_rejected(client):
    r = client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[bad]", "platform": "blackberry"},
    )
    assert r.status_code == 422


def test_reregister_same_token_updates_platform(client, db_session, test_user):
    # Initial registration as ios
    client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[same]", "platform": "ios"},
    )
    # Re-register same token as android (device reinstall on another OS is impossible
    # in practice for the same token, but the handler must still update the field
    # idempotently rather than create a duplicate row).
    client.post(
        "/notifications/push-token",
        json={"token": "ExponentPushToken[same]", "platform": "android"},
    )
    rows = db_session.execute(
        select(PushToken).where(PushToken.token == "ExponentPushToken[same]")
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].platform == "android"
