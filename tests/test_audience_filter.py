"""PUSH-03 — audience segment targeting via role_filter on /admin/push/broadcast.

Verifies that the role_filter field on BroadcastPushIn correctly scopes the
fan-out to users matching the requested role. Mocks send_push so we exercise
the routing logic without hitting Expo.

Phase 13 gap closure (gap 6c) — extends existing 3 tests with 5 new tests for
age-band audience filter (Tests 4-8). The new tests pin the semantics of
age_band="all"|"18-24"|"25-34"|"35-44"|"45+" intersected with role_filter.

Reference ages on 2026-04-16 (project currentDate):
  - DOB 2005-01-01 → age 21 → band "18-24"
  - DOB 1995-01-01 → age 31 → band "25-34"
  - DOB 1985-01-01 → age 41 → band "35-44"
  - DOB 1970-01-01 → age 56 → band "45+"
  - DOB None       → excluded from any banded send
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.core.enums import UserRole
from app.core.deps import require_admin
from app.main import app
from app.models.user import User
from app.models.push_token import PushToken


@pytest.fixture()
def admin_client(client, db_session, test_user):
    """Promote the conftest test_user to admin so /admin/push/broadcast accepts the call."""
    test_user.role = UserRole.admin
    db_session.commit()
    app.dependency_overrides[require_admin] = lambda: test_user
    yield client
    app.dependency_overrides.pop(require_admin, None)


def _seed_user_with_token(
    db,
    email: str,
    role: UserRole,
    platform: str | None,
    date_of_birth: date | None = None,
) -> User:
    """Create a User + PushToken for audience filter tests.

    `date_of_birth` is optional — the 3 original tests don't pass it (defaults to None),
    so existing call-sites remain unchanged.
    """
    u = User(
        email=email,
        password_hash="x",
        full_name=email,
        role=role,
        date_of_birth=date_of_birth,
    )
    db.add(u)
    db.flush()
    db.add(PushToken(user_id=u.id, token=f"t-{email}", platform=platform))
    db.commit()
    return u


# --------------------------------------------------------------------------
# Original 3 tests (PUSH-03 role_filter coverage) — unchanged
# --------------------------------------------------------------------------

def test_no_role_filter_sends_to_all(admin_client, db_session):
    _seed_user_with_token(db_session, "a@x", UserRole.attendee, "ios")
    _seed_user_with_token(db_session, "s@x", UserRole.speaker, "android")
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post("/admin/push/broadcast", json={"title": "hi", "body": "y"})
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 2
    assert mock_send.call_count == 2


def test_role_filter_speaker_only(admin_client, db_session):
    _seed_user_with_token(db_session, "a@x", UserRole.attendee, "ios")
    _seed_user_with_token(db_session, "s1@x", UserRole.speaker, "android")
    _seed_user_with_token(db_session, "s2@x", UserRole.speaker, "ios")
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "role_filter": "speaker"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 2
    assert mock_send.call_count == 2


def test_role_filter_exhibitor_excludes_attendees(admin_client, db_session):
    _seed_user_with_token(db_session, "a@x", UserRole.attendee, "ios")
    _seed_user_with_token(db_session, "e@x", UserRole.exhibitor, "android")
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "role_filter": "exhibitor"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 1
    assert mock_send.call_count == 1


# --------------------------------------------------------------------------
# New 5 tests (gap 6c — age-band audience filter)
# RED phase: these tests post age_band in the JSON body.
# Until Task 2 adds age_band to BroadcastPushIn, Pydantic rejects the
# unknown field with HTTP 422. That 422 response IS the RED signal.
# After Task 2 (GREEN), all 5 tests pass.
# --------------------------------------------------------------------------

def test_age_band_all_includes_all(admin_client, db_session):
    """age_band='all' is the no-op default — all users with push tokens are included,
    even those whose date_of_birth is NULL (we cannot bucket them but 'all' skips bucketing).
    Pins bucket boundary: band 'all' → (None, None) range → no DOB filter applied.
    """
    _seed_user_with_token(db_session, "u21@x", UserRole.attendee, "ios", date(2005, 1, 1))
    _seed_user_with_token(db_session, "u31@x", UserRole.attendee, "android", date(1995, 1, 1))
    _seed_user_with_token(db_session, "null@x", UserRole.attendee, "ios", None)
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "age_band": "all"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 3
    assert mock_send.call_count == 3


def test_age_band_18_24_excludes_other_bands(admin_client, db_session):
    """age_band='18-24' (age <25 on 2026-04-16) includes only the 21-year-old.
    Pins bucket boundary: <25 → only DOB > (today - 25y) AND DOB <= (today - 18y).
    """
    u21 = _seed_user_with_token(db_session, "u21@x", UserRole.attendee, "ios", date(2005, 1, 1))
    _seed_user_with_token(db_session, "u31@x", UserRole.attendee, "android", date(1995, 1, 1))
    _seed_user_with_token(db_session, "u41@x", UserRole.attendee, "ios", date(1985, 1, 1))
    _seed_user_with_token(db_session, "u56@x", UserRole.attendee, "android", date(1970, 1, 1))
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "age_band": "18-24"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent_count"] == 1, f"Expected 1, got {body['sent_count']}"
    assert mock_send.call_count == 1
    # Verify the single call targeted the 21-year-old specifically.
    called_user_id = mock_send.call_args_list[0].kwargs.get("user_id") or mock_send.call_args_list[0].args[1]
    assert called_user_id == u21.id, f"Expected user_id={u21.id}, got {called_user_id}"


def test_age_band_combined_with_role(admin_client, db_session):
    """Role filter AND age-band filter are intersected (AND, not OR).
    Only the speaker aged 21 should receive the push — the attendee aged 21 and
    speakers aged 31/56 are all excluded.
    Pins bucket boundary: role='speaker' AND band='18-24' → 1 user.
    """
    _seed_user_with_token(db_session, "att21@x", UserRole.attendee, "ios", date(2005, 1, 1))
    spk21 = _seed_user_with_token(db_session, "spk21@x", UserRole.speaker, "android", date(2005, 6, 1))
    _seed_user_with_token(db_session, "spk31@x", UserRole.speaker, "ios", date(1995, 1, 1))
    _seed_user_with_token(db_session, "spk56@x", UserRole.speaker, "android", date(1970, 1, 1))
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "role_filter": "speaker", "age_band": "18-24"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent_count"] == 1, f"Expected 1 (speaker+18-24), got {body['sent_count']}"
    assert mock_send.call_count == 1
    called_user_id = mock_send.call_args_list[0].kwargs.get("user_id") or mock_send.call_args_list[0].args[1]
    assert called_user_id == spk21.id, f"Expected speaker21 id={spk21.id}, got {called_user_id}"


def test_age_band_excludes_users_without_dob(admin_client, db_session):
    """Users with date_of_birth IS NULL are EXCLUDED from any banded send.
    Pins NULL-DOB exclusion semantic: NULL DOB → cannot determine band → not included.
    Sending with age_band='18-24' should include the 21-year-old and exclude the NULL user.
    Sending with age_band='25-34' should include nobody (the 21-year-old is outside this band).
    """
    u21 = _seed_user_with_token(db_session, "u21@x", UserRole.attendee, "ios", date(2005, 1, 1))
    _seed_user_with_token(db_session, "null@x", UserRole.attendee, "android", None)

    # Send to 18-24 → should reach u21 only.
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "age_band": "18-24"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 1
    assert mock_send.call_count == 1

    # Send to 25-34 → nobody (u21 is in 18-24; NULL user is excluded).
    with patch("app.api.routes.admin_push.send_push") as mock_send:
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "age_band": "25-34"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["sent_count"] == 0
    assert mock_send.call_count == 0


def test_breakdown_respects_age_band(admin_client, db_session):
    """The device breakdown (total/iOS/Android/unknown) reflects the AGE-FILTERED set.
    Proves breakdown is computed AFTER the age filter, not on the full user base.

    Seed: 4 users (2x age-21 on iOS/Android, 1x age-31 on iOS, 1x NULL-DOB on Android).
    Send with age_band='18-24' → only the 2 age-21 users are included.
    Expected: total_devices=2, ios_count=1, android_count=1, unknown_count=0, sent_count=2.
    If breakdown was computed on the UNFILTERED set we'd see total_devices=4.
    """
    _seed_user_with_token(db_session, "u21ios@x", UserRole.attendee, "ios", date(2005, 1, 1))
    _seed_user_with_token(db_session, "u21and@x", UserRole.attendee, "android", date(2005, 6, 1))
    _seed_user_with_token(db_session, "u31ios@x", UserRole.attendee, "ios", date(1995, 1, 1))
    _seed_user_with_token(db_session, "nulland@x", UserRole.attendee, "android", None)

    with patch("app.api.routes.admin_push.send_push"):
        r = admin_client.post(
            "/admin/push/broadcast",
            json={"title": "hi", "body": "y", "age_band": "18-24"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent_count"] == 2, f"Expected sent_count=2, got {body['sent_count']}"
    assert body["total_devices"] == 2, (
        f"total_devices={body['total_devices']} — breakdown must be computed AFTER age filter"
    )
    assert body["ios_count"] == 1, f"Expected ios_count=1, got {body['ios_count']}"
    assert body["android_count"] == 1, f"Expected android_count=1, got {body['android_count']}"
    assert body["unknown_count"] == 0, f"Expected unknown_count=0, got {body['unknown_count']}"
