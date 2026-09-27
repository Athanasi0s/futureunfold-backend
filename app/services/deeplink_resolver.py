"""Deeplink template resolver (Phase 13 — PUSH-01, PUSH-02).

Admin picks a template name; this module resolves it to a literal deeplink path
at send time, querying current DB state for dynamic templates.

Raises EmptyTargetError when a dynamic template has no target (e.g. no trending
group in the last 7 days). The route layer converts this to HTTP 400.

Note on model naming: the festival app's group-membership table is
``group_members`` (model ``GroupMember``) — there is no ``UserGroup``. The
program-session table is ``sessions`` (model ``Session``); we alias as
``ProgramSession`` here to avoid clashing with SQLAlchemy ``Session``.

# CONTRACT: every path emitted by these resolvers MUST start with one of the
# prefixes in festapp-mobile/features/notifications/hooks/useNotificationListener.ts
# KNOWN_DEEPLINK_PREFIXES. If you add a new resolver, update both files and the
# contract test test_all_resolved_paths_are_in_mobile_allowlist.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_message import GroupMessage
from app.models.session import Session as ProgramSession
from app.models.user_agenda import UserAgenda


class EmptyTargetError(RuntimeError):
    """Raised when a dynamic template resolves to zero rows.

    The admin push route converts this into a 400 Bad Request with the
    canonical message from ``TEMPLATE_ERROR_MESSAGES`` so the admin UI can
    explain why the broadcast was blocked.
    """


DeeplinkTemplate = Literal[
    "none",
    "trending_group",
    "trending_session",
    "biggest_group",
    "biggest_group_chat",
    "biggest_session",
    "leaderboard",
    "schedule",
]


TEMPLATE_ERROR_MESSAGES: dict[str, str] = {
    "trending_group": "No trending group in the last 7 days — pick a different link destination.",
    "trending_session": "No trending session in the last 7 days — pick a different link destination.",
    "biggest_group": "No groups exist yet — pick a different link destination.",
    "biggest_group_chat": "No group chat has messages yet — pick a different link destination.",
    "biggest_session": "No session has attendees yet — pick a different link destination.",
}


def _since_7d() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=7)


# ---------------------------------------------------------------------------
# Dynamic resolvers
# ---------------------------------------------------------------------------

def _trending_group(db: DBSession) -> str:
    """Group with the most NEW members in the last 7 days."""
    row = db.execute(
        select(GroupMember.group_id, func.count().label("n"))
        .where(GroupMember.joined_at >= _since_7d())
        .group_by(GroupMember.group_id)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    if row is None:
        raise EmptyTargetError(TEMPLATE_ERROR_MESSAGES["trending_group"])
    return f"/group-details?id={row[0]}"


def _trending_session(db: DBSession) -> str:
    """Session with the most NEW agenda favourites in the last 7 days.

    Excludes cancelled sessions (``is_cancelled=True``) because
    ``GET /sessions/{id}`` returns 404 for those — a deeplink pointing at a
    cancelled session would land the user on a retry page (UAT Phase 13 post-close).
    """
    row = db.execute(
        select(UserAgenda.session_id, func.count().label("n"))
        .join(ProgramSession, ProgramSession.id == UserAgenda.session_id)
        .where(UserAgenda.created_at >= _since_7d())
        .where(ProgramSession.is_cancelled.is_(False))
        .group_by(UserAgenda.session_id)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    if row is None:
        raise EmptyTargetError(TEMPLATE_ERROR_MESSAGES["trending_session"])
    return f"/session/{row[0]}"


def _biggest_group(db: DBSession) -> str:
    """Group with the highest overall member count."""
    row = db.execute(
        select(Group.id, func.count(GroupMember.id).label("n"))
        .join(GroupMember, GroupMember.group_id == Group.id)
        .group_by(Group.id)
        .order_by(func.count(GroupMember.id).desc())
        .limit(1)
    ).first()
    if row is None:
        raise EmptyTargetError(TEMPLATE_ERROR_MESSAGES["biggest_group"])
    return f"/group-details?id={row[0]}"


def _biggest_group_chat(db: DBSession) -> str:
    """Group whose chat has accumulated the most messages."""
    row = db.execute(
        select(GroupMessage.group_id, func.count().label("n"))
        .group_by(GroupMessage.group_id)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    if row is None:
        raise EmptyTargetError(TEMPLATE_ERROR_MESSAGES["biggest_group_chat"])
    return f"/group-details?id={row[0]}"


def _biggest_session(db: DBSession) -> str:
    """Session with the most overall agenda favourites.

    Excludes cancelled sessions (``is_cancelled=True``) because
    ``GET /sessions/{id}`` returns 404 for those — a deeplink pointing at a
    cancelled session would land the user on a retry page (UAT Phase 13 post-close).
    """
    row = db.execute(
        select(ProgramSession.id, func.count(UserAgenda.id).label("n"))
        .join(UserAgenda, UserAgenda.session_id == ProgramSession.id)
        .where(ProgramSession.is_cancelled.is_(False))
        .group_by(ProgramSession.id)
        .order_by(func.count(UserAgenda.id).desc())
        .limit(1)
    ).first()
    if row is None:
        raise EmptyTargetError(TEMPLATE_ERROR_MESSAGES["biggest_session"])
    return f"/session/{row[0]}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RESOLVERS: dict[str, Callable[[DBSession], str | None]] = {
    "none": lambda _db: None,
    "trending_group": _trending_group,
    "trending_session": _trending_session,
    "biggest_group": _biggest_group,
    "biggest_group_chat": _biggest_group_chat,
    "biggest_session": _biggest_session,
    "leaderboard": lambda _db: "/profile/leaderboard",
    "schedule": lambda _db: "/(tabs)/(schedule)",
}


def resolve(template: str, db: DBSession) -> str | None:
    """Resolve a template name to a deeplink path. Raises on unknown / empty."""
    if template not in RESOLVERS:
        raise ValueError(f"Unknown deeplink template: {template!r}")
    return RESOLVERS[template](db)
