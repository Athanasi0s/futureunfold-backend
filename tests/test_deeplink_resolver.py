"""Unit tests for deeplink template resolver (PUSH-01, PUSH-02).

Exercises the eight templates the admin push UI exposes:
  none / leaderboard / schedule         — static, no DB hit
  trending_group / trending_session     — last-7-day windowed
  biggest_group / biggest_group_chat /
    biggest_session                     — overall counts

All dynamic templates raise EmptyTargetError when the underlying table is
empty so the route layer can convert to HTTP 400.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.session import Session as ProgramSession
from app.models.user_agenda import UserAgenda
from app.services.deeplink_resolver import resolve, EmptyTargetError, RESOLVERS


# ---------------------------------------------------------------------------
# Static templates
# ---------------------------------------------------------------------------

def test_resolvers_dict_has_eight_keys():
    assert set(RESOLVERS.keys()) == {
        "none",
        "trending_group",
        "trending_session",
        "biggest_group",
        "biggest_group_chat",
        "biggest_session",
        "leaderboard",
        "schedule",
    }


def test_none_returns_none(db_session):
    assert resolve("none", db_session) is None


def test_leaderboard_static(db_session):
    assert resolve("leaderboard", db_session) == "/profile/leaderboard"


def test_schedule_static(db_session):
    assert resolve("schedule", db_session) == "/(tabs)/(schedule)"


def test_unknown_template_raises(db_session):
    with pytest.raises(ValueError):
        resolve("totally_fake_template", db_session)


# ---------------------------------------------------------------------------
# Dynamic templates — empty DB
# ---------------------------------------------------------------------------

def test_trending_group_empty_raises(db_session):
    with pytest.raises(EmptyTargetError):
        resolve("trending_group", db_session)


def test_biggest_group_empty_raises(db_session):
    with pytest.raises(EmptyTargetError):
        resolve("biggest_group", db_session)


# ---------------------------------------------------------------------------
# Dynamic templates — populated DB
# ---------------------------------------------------------------------------

def _make_group(db, ref_suffix: str) -> Group:
    g = Group(
        group_type="topic",
        ref_key=f"topic:{ref_suffix}",
        title=f"Group {ref_suffix}",
    )
    db.add(g)
    db.flush()
    return g


def test_trending_group_returns_highest(db_session, test_user):
    # Group A gets 3 recent joins; Group B gets 1.
    g_a = _make_group(db_session, "a")
    g_b = _make_group(db_session, "b")
    # Capture IDs BEFORE commit so we don't trigger a refresh that eager-loads
    # the Group.interests selectin relationship (group_interests table is not
    # whitelisted on the SQLite test engine).
    g_a_id = g_a.id
    g_b_id = g_b.id
    now = datetime.now(timezone.utc)
    # Use distinct user records — GroupMember has uq(group_id, user_id).
    from app.models.user import User
    from app.core.enums import UserRole
    extras = []
    for i in range(3):
        u = User(
            email=f"u{i}@x",
            password_hash="x",
            full_name=f"u{i}",
            role=UserRole.attendee,
        )
        db_session.add(u)
        db_session.flush()
        extras.append(u)
    db_session.add_all([
        GroupMember(group_id=g_a_id, user_id=extras[0].id, joined_at=now),
        GroupMember(group_id=g_a_id, user_id=extras[1].id, joined_at=now),
        GroupMember(group_id=g_a_id, user_id=extras[2].id, joined_at=now),
        GroupMember(group_id=g_b_id, user_id=test_user.id, joined_at=now),
    ])
    db_session.commit()
    assert resolve("trending_group", db_session) == f"/group-details?id={g_a_id}"


def test_biggest_group_returns_highest_overall(db_session, test_user):
    """Even with old joins (outside trending window), biggest_group counts ALL members."""
    from app.models.user import User
    from app.core.enums import UserRole
    g_a = _make_group(db_session, "big-a")
    g_b = _make_group(db_session, "big-b")
    g_a_id = g_a.id
    g_b_id = g_b.id
    old = datetime.now(timezone.utc) - timedelta(days=30)
    extras = []
    for i in range(5):
        u = User(
            email=f"big{i}@x",
            password_hash="x",
            full_name=f"big{i}",
            role=UserRole.attendee,
        )
        db_session.add(u)
        db_session.flush()
        extras.append(u)
    for u in extras:
        db_session.add(GroupMember(group_id=g_a_id, user_id=u.id, joined_at=old))
    db_session.add(GroupMember(group_id=g_b_id, user_id=test_user.id, joined_at=old))
    db_session.commit()
    assert resolve("biggest_group", db_session) == f"/group-details?id={g_a_id}"


# ---------------------------------------------------------------------------
# Full-template coverage — pin all 8 output formats (gap 6b, Plan 13-11)
# ---------------------------------------------------------------------------

def _seed_full_dataset(db_session, test_user):
    """Seed enough rows to make every dynamic template succeed."""
    from app.models.user import User
    from app.core.enums import UserRole

    now = datetime.now(timezone.utc)

    # One extra user so membership/agenda rows can reference distinct IDs
    extra = User(email="seed_extra@x", password_hash="x", full_name="Extra", role=UserRole.attendee)
    db_session.add(extra)
    db_session.flush()

    # Group with one recent member (trending_group) and one message (biggest_group_chat)
    g = Group(group_type="topic", ref_key="topic:seed", title="Seed Group")
    db_session.add(g)
    db_session.flush()
    g_id = g.id

    db_session.add(GroupMember(group_id=g_id, user_id=test_user.id, joined_at=now))
    db_session.add(GroupMessage(group_id=g_id, sender_id=test_user.id, content="hi"))

    # Session with one recent agenda entry (trending_session) and one overall (biggest_session)
    s = ProgramSession(
        title="Seed Session",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
    )
    db_session.add(s)
    db_session.flush()
    s_id = s.id

    db_session.add(UserAgenda(session_id=s_id, user_id=test_user.id, created_at=now))
    db_session.commit()
    return g_id, s_id


def test_all_resolvers_return_mobile_compatible_paths(db_session, test_user):
    """Pin the EXACT output format for all 8 templates (gap 6b regression guard)."""
    g_id, s_id = _seed_full_dataset(db_session, test_user)

    expected_prefixes = {
        "none": None,
        "trending_group": "/group-details?id=",
        "trending_session": "/session/",
        "biggest_group": "/group-details?id=",
        "biggest_group_chat": "/group-details?id=",
        "biggest_session": "/session/",
        "leaderboard": "/profile/leaderboard",
        "schedule": "/(tabs)/(schedule)",
    }

    for template, prefix in expected_prefixes.items():
        result = resolve(template, db_session)
        if prefix is None:
            assert result is None, f"{template} should return None, got {result!r}"
        else:
            assert result is not None, f"{template} returned None, expected prefix {prefix!r}"
            assert result.startswith(prefix), (
                f"{template} returned {result!r}, expected prefix {prefix!r}"
            )


def test_all_resolved_paths_are_in_mobile_allowlist(db_session, test_user):
    """Contract test: backend resolver outputs must be a subset of the mobile allowlist.

    MIRROR of festapp-mobile/features/notifications/hooks/useNotificationListener.ts
    KNOWN_DEEPLINK_PREFIXES. If you add an entry on either side, update both.
    CI fails immediately if a resolver emits a path that the mobile handler would
    fall back to home for.
    """
    # MIRROR of KNOWN_DEEPLINK_PREFIXES in useNotificationListener.ts
    MOBILE_ALLOWLIST = (
        "/group-details",
        "/group-chat",
        "/session/",
        "/profile/",
        "/(tabs)/",
        "/dm-chat",
        "/networking",
        "/notifications",
    )

    _seed_full_dataset(db_session, test_user)

    for template, resolver in RESOLVERS.items():
        try:
            path = resolver(db_session)
        except EmptyTargetError:
            continue  # dynamic template with no data — fixture coverage handles this elsewhere
        if path is None:
            continue  # "none" template
        assert any(path.startswith(prefix) for prefix in MOBILE_ALLOWLIST), (
            f"Template {template!r} resolved to {path!r}, which does not match any "
            f"mobile allowlist prefix. Update KNOWN_DEEPLINK_PREFIXES in "
            f"useNotificationListener.ts AND this test mirror."
        )


# ---------------------------------------------------------------------------
# Cancelled-session exclusion (post-UAT guard)
# ---------------------------------------------------------------------------
# GET /sessions/{id} returns 404 for is_cancelled=True sessions (Phase 12 soft-
# delete pattern). Without filtering, a cancelled session at the top of the
# agenda-count leaderboard would produce a deeplink landing the user on the
# mobile retry page. These tests pin the filter so a regression re-introduces
# the 404 bug immediately.

def test_trending_session_skips_cancelled(db_session, test_user):
    """If the top-trending session is cancelled, pick the next live one."""
    from app.models.user import User
    from app.core.enums import UserRole

    now = datetime.now(timezone.utc)

    # Cancelled session — 3 recent agenda favourites
    s_cancelled = ProgramSession(
        title="Cancelled Session",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
        is_cancelled=True,
    )
    # Live session — 1 recent agenda favourite
    s_live = ProgramSession(
        title="Live Session",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
    )
    db_session.add_all([s_cancelled, s_live])
    db_session.flush()
    s_cancelled_id = s_cancelled.id
    s_live_id = s_live.id

    extras = []
    for i in range(3):
        u = User(
            email=f"tcs{i}@x",
            password_hash="x",
            full_name=f"tcs{i}",
            role=UserRole.attendee,
        )
        db_session.add(u)
        db_session.flush()
        extras.append(u)

    db_session.add_all([
        UserAgenda(session_id=s_cancelled_id, user_id=extras[0].id, created_at=now),
        UserAgenda(session_id=s_cancelled_id, user_id=extras[1].id, created_at=now),
        UserAgenda(session_id=s_cancelled_id, user_id=extras[2].id, created_at=now),
        UserAgenda(session_id=s_live_id, user_id=test_user.id, created_at=now),
    ])
    db_session.commit()

    # Cancelled session has more favourites, but resolver must skip it.
    assert resolve("trending_session", db_session) == f"/session/{s_live_id}"


def test_biggest_session_skips_cancelled(db_session, test_user):
    """If the biggest-overall session is cancelled, pick the next live one."""
    from app.models.user import User
    from app.core.enums import UserRole

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    s_cancelled = ProgramSession(
        title="Cancelled Overall",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
        is_cancelled=True,
    )
    s_live = ProgramSession(
        title="Live Overall",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
    )
    db_session.add_all([s_cancelled, s_live])
    db_session.flush()
    s_cancelled_id = s_cancelled.id
    s_live_id = s_live.id

    extras = []
    for i in range(5):
        u = User(
            email=f"bcs{i}@x",
            password_hash="x",
            full_name=f"bcs{i}",
            role=UserRole.attendee,
        )
        db_session.add(u)
        db_session.flush()
        extras.append(u)

    for u in extras:
        db_session.add(UserAgenda(session_id=s_cancelled_id, user_id=u.id, created_at=old))
    db_session.add(UserAgenda(session_id=s_live_id, user_id=test_user.id, created_at=old))
    db_session.commit()

    assert resolve("biggest_session", db_session) == f"/session/{s_live_id}"


def test_trending_session_all_cancelled_raises(db_session, test_user):
    """If every session with agenda favourites is cancelled, treat as empty."""
    now = datetime.now(timezone.utc)
    s = ProgramSession(
        title="All-Cancelled",
        start_time=now,
        end_time=now + timedelta(hours=1),
        type="talk",
        is_cancelled=True,
    )
    db_session.add(s)
    db_session.flush()
    db_session.add(UserAgenda(session_id=s.id, user_id=test_user.id, created_at=now))
    db_session.commit()

    with pytest.raises(EmptyTargetError):
        resolve("trending_session", db_session)
