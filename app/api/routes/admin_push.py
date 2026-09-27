"""Admin push broadcast endpoint (Phase 13 — PUSH-01..04).

Differences from the pre-Phase-13 handler:
  - PUSH-01 / T-13-02: replaces the free-text ``deeplink`` field with a
    ``deeplink_template`` enum. Pydantic rejects any value outside the 8 known
    templates with HTTP 422 — closes the deeplink-injection threat.
  - PUSH-02: server resolves the template at send time via
    ``deeplink_resolver.resolve``. Empty dynamic targets surface as HTTP 400
    with the canonical message from ``TEMPLATE_ERROR_MESSAGES``.
  - PUSH-03: ``role_filter`` continues to scope the fan-out (existing semantic).
  - PUSH-04: response includes total / iOS / Android / unknown device counts
    computed from ``push_tokens.platform`` (added by Plan 13-02 migration
    ``t6a7b8c9d0e1``).
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.models.push_token import PushToken
from app.services.push import send_push
from app.services.deeplink_resolver import (
    resolve as resolve_deeplink,
    EmptyTargetError,
)
from app.api.routes.admin import log_admin_action
from app.api.schemas import BroadcastPushIn, BroadcastPushOut

router = APIRouter()


# ------------------------------------------------------------------
# Helper: map age-band literal to inclusive (min_dob, max_dob) range
# ------------------------------------------------------------------
def _age_band_dob_range(today: date, band: str) -> tuple[date | None, date | None]:
    """Map an age-band literal to an inclusive (min_dob, max_dob) range.

    Boundaries mirror admin.py demographics buckets exactly:
      18-24 → age in [18, 24]   → DOB in (today - 25y, today - 18y]
      25-34 → age in [25, 34]   → DOB in (today - 35y, today - 25y]
      35-44 → age in [35, 44]   → DOB in (today - 45y, today - 35y]
      45+   → age >= 45         → DOB <= today - 45y
      all   → no filter         → returns (None, None)

    Uses date arithmetic (timedelta days) which works on both SQLite (tests)
    and Postgres (production). The integer-year approximation matches
    admin.py's date_part("year", age()) truncation — both are subject to
    leap-year rounding at exact birthdays, which is acceptable for bulk
    audience targeting.
    """
    if band == "all":
        return (None, None)

    def _years_ago(years: int) -> date:
        return today - timedelta(days=years * 365)

    if band == "18-24":
        # Born after (today-25y) AND on or before (today-18y)
        return (_years_ago(25) + timedelta(days=1), _years_ago(18))
    if band == "25-34":
        return (_years_ago(35) + timedelta(days=1), _years_ago(25))
    if band == "35-44":
        return (_years_ago(45) + timedelta(days=1), _years_ago(35))
    if band == "45+":
        return (None, _years_ago(45))
    # Defensive — Pydantic Literal should have already rejected this.
    raise ValueError(f"Unknown age_band: {band!r}")


# ------------------------------------------------------------------
# Helper: per-platform device breakdown for a fan-out user_id list
# ------------------------------------------------------------------
def count_devices(db: Session, user_ids: list[int]) -> dict[str, int]:
    """Return a breakdown of push_tokens platforms for the fan-out set.

    Buckets: ``ios`` / ``android`` / ``unknown`` (legacy NULL or future ``web``)
    plus ``total`` for convenience. Empty input → all zeros.
    """
    breakdown = {"ios": 0, "android": 0, "unknown": 0, "total": 0}
    if not user_ids:
        return breakdown
    rows = db.execute(
        select(PushToken.platform, func.count(PushToken.id))
        .where(PushToken.user_id.in_(user_ids))
        .group_by(PushToken.platform)
    ).all()
    for platform, n in rows:
        key = platform if platform in ("ios", "android") else "unknown"
        breakdown[key] += int(n)
        breakdown["total"] += int(n)
    return breakdown


# ------------------------------------------------------------------
# POST /admin/push/broadcast
# ------------------------------------------------------------------
@router.post("/admin/push/broadcast", response_model=BroadcastPushOut)
def broadcast_push(
    data: BroadcastPushIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    # 1) Resolve deeplink template at send time (PUSH-02). Reject empty dynamic
    #    targets with a friendly 400 so the admin UI can prompt the picker again.
    try:
        resolved_deeplink = resolve_deeplink(data.deeplink_template, db)
    except EmptyTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2) Build fan-out user_ids, scoped by role_filter when set (PUSH-03)
    #    AND age_band when set (Phase 13 gap 6c).
    q = (
        select(User.id)
        .join(PushToken, PushToken.user_id == User.id)
        .distinct()
    )
    if data.role_filter is not None:
        q = q.where(User.role == data.role_filter)

    # Age-band filter (gap 6c). NULL date_of_birth is excluded for any band
    # other than "all" — we cannot bucket users with missing DOB.
    min_dob, max_dob = _age_band_dob_range(date.today(), data.age_band)
    if data.age_band != "all":
        q = q.where(User.date_of_birth.isnot(None))
        if min_dob is not None:
            q = q.where(User.date_of_birth >= min_dob)
        if max_dob is not None:
            q = q.where(User.date_of_birth <= max_dob)

    user_ids: list[int] = list(db.execute(q).scalars().all())

    # 3) Fire pushes one user at a time (existing semantic from pre-Phase-13).
    sent_count = 0
    failed_count = 0
    for user_id in user_ids:
        try:
            send_push(
                db=db,
                user_id=user_id,
                title=data.title,
                body=data.body,
                notif_type="broadcast",
                deeplink=resolved_deeplink,
            )
            sent_count += 1
        except Exception:
            failed_count += 1

    # 4) Per-platform device breakdown (PUSH-04).
    breakdown = count_devices(db, user_ids)

    # 5) Audit log — full context for post-mortem traceability.
    log_admin_action(
        db,
        admin.id,
        "broadcast_push",
        detail={
            "title": data.title,
            "body": data.body,
            "role_filter": data.role_filter.value if data.role_filter else None,
            "age_band": data.age_band,
            "deeplink_template": data.deeplink_template,
            "resolved_deeplink": resolved_deeplink,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_devices": breakdown["total"],
            "ios_count": breakdown["ios"],
            "android_count": breakdown["android"],
            "unknown_count": breakdown["unknown"],
        },
    )
    db.commit()

    return BroadcastPushOut(
        sent_count=sent_count,
        message=f"Broadcast sent to {sent_count} users.",
        total_devices=breakdown["total"],
        ios_count=breakdown["ios"],
        android_count=breakdown["android"],
        unknown_count=breakdown["unknown"],
        resolved_deeplink=resolved_deeplink,
    )
