import re
from datetime import datetime, timedelta, timezone, date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func, or_, and_, cast, Date, case, select
from typing import Optional, Any, Literal

from app.core.deps import get_db, require_admin, require_moderator_scope
from app.core.feature_flags import FEATURE_REGISTRY, get_merged_flags, apply_cascade
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.app_config import AppConfig
from app.models.ticket_package import TicketPackage
from app.models.group import Group
from app.models.session import Session as ProgramSession
from app.models.session_chat_message import SessionChatMessage
from app.models.session_question import SessionQuestion
from app.core.enums import UserRole
from app.models.user_report import UserReport
from app.models.user_interest import UserInterest
from app.models.interest import Interest
from app.models.group_member import GroupMember
from app.models.message import Message
from app.models.meeting import Meeting
from app.models.scan_log import ScanLog
from app.models.user_agenda import UserAgenda
from app.models.ticket import Ticket
from app.models.poll import Poll
from pydantic import BaseModel, Field
from app.api.schemas import (
    PaginatedUsersOut,
    AdminUserOut,
    AuditLogOut,
    StatsOut,
    TicketPackageIn,
    TicketPackageUpdateIn,
    AdminRoleChangeIn,
    DemographicsOut,
    GroupRankingsOut,
    ModeratorPermissionsIn,
    ModeratorPermissionsOut,
    SessionOut,
    SessionImpactOut,
    NotifyUpdateIn,
)
from app.api.routes.program import _session_to_out
from app.models.group_message import GroupMessage

router = APIRouter()

VALID_THEME_PRESETS = {
    "midnight-indigo",
    "festival-fire",
    "ocean-breeze",
    "forest-canopy",
    "sunset-glow",
    "arctic-frost",
    "royal-purple",
    "desert-sand",
    "neon-city",
    "classic-dark",
    "electric-blue",
    "athens-sunrise",
    "classic-mono",
}


def log_admin_action(db, admin_id, action, target_type=None, target_id=None, detail=None):
    db.add(AuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
    ))


# ------------------------------------------------------------------
# 1. GET /admin/users  --  Paginated user list
# ------------------------------------------------------------------
@router.get("/admin/users", response_model=PaginatedUsersOut)
def list_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    blocked: Optional[bool] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(User)
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if role:
        q = q.filter(User.role == role)
    if blocked is not None:
        q = q.filter(User.is_blocked == blocked)

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        AdminUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_blocked=u.is_blocked,
            points=u.points,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]
    return PaginatedUsersOut(total=total, offset=offset, limit=limit, items=items)


# ------------------------------------------------------------------
# 2. POST /admin/users/{user_id}/block
# ------------------------------------------------------------------
@router.post("/admin/users/{user_id}/block")
def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_blocked = True
    log_admin_action(db, admin.id, "block_user", target_type="user", target_id=user_id)
    db.commit()
    return {"status": "blocked"}


# ------------------------------------------------------------------
# 3. POST /admin/users/{user_id}/unblock
# ------------------------------------------------------------------
@router.post("/admin/users/{user_id}/unblock")
def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_blocked = False
    log_admin_action(db, admin.id, "unblock_user", target_type="user", target_id=user_id)
    db.commit()
    return {"status": "unblocked"}


# ------------------------------------------------------------------
# 4. DELETE /admin/users/{user_id}
# ------------------------------------------------------------------
@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    log_admin_action(
        db, admin.id, "delete_user",
        target_type="user", target_id=user_id,
        detail={"email": user.email},
    )
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


# ------------------------------------------------------------------
# 5. GET /admin/stats
# ------------------------------------------------------------------
@router.get("/admin/stats", response_model=StatsOut)
def get_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    total_users = db.query(func.count(User.id)).scalar() or 0
    role_rows = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    users_by_role = {str(role): count for role, count in role_rows}

    # Role breakdown with percentages
    role_breakdown = [
        {"role": str(r), "count": c, "percentage": round(c / max(total_users, 1) * 100, 1)}
        for r, c in role_rows
    ]

    total_groups = db.query(func.count(Group.id)).scalar() or 0
    total_sessions = db.query(func.count(ProgramSession.id)).scalar() or 0

    # Polls
    try:
        total_polls = db.query(func.count(Poll.id)).scalar() or 0
    except Exception:
        total_polls = 0

    # Top interests (top 20)
    try:
        interest_rows = (
            db.query(Interest.name, func.count(UserInterest.user_id))
            .join(UserInterest, Interest.id == UserInterest.interest_id)
            .group_by(Interest.name)
            .order_by(func.count(UserInterest.user_id).desc())
            .limit(20)
            .all()
        )
        top_interests = [{"name": name, "count": cnt} for name, cnt in interest_rows]
    except Exception:
        top_interests = []

    # Group membership stats
    try:
        total_group_memberships = db.query(func.count(GroupMember.id)).scalar() or 0
        avg_members_per_group = round(total_group_memberships / max(total_groups, 1), 1)
    except Exception:
        total_group_memberships = 0
        avg_members_per_group = 0.0

    # DMs
    try:
        total_dms = db.query(func.count(Message.id)).scalar() or 0
    except Exception:
        total_dms = 0

    # Meetings
    try:
        total_meetings = db.query(func.count(Meeting.id)).scalar() or 0
    except Exception:
        total_meetings = 0

    # QR Scans
    try:
        total_qr_scans = db.query(func.count(ScanLog.id)).scalar() or 0
    except Exception:
        total_qr_scans = 0

    # Agenda saves (session check-ins / favorites)
    try:
        total_agenda_saves = db.query(func.count(UserAgenda.id)).scalar() or 0
    except Exception:
        total_agenda_saves = 0

    # Points stats
    try:
        avg_points = round(float(db.query(func.avg(User.points)).scalar() or 0), 1)
        max_points = db.query(func.max(User.points)).scalar() or 0
        users_with_points = db.query(func.count(User.id)).filter(User.points > 0).scalar() or 0
    except Exception:
        avg_points = 0.0
        max_points = 0
        users_with_points = 0

    # Ticket stats
    try:
        total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
        used_tickets = db.query(func.count(Ticket.id)).filter(Ticket.status == "used").scalar() or 0
        active_tickets = db.query(func.count(Ticket.id)).filter(Ticket.status == "active").scalar() or 0
    except Exception:
        total_tickets = 0
        used_tickets = 0
        active_tickets = 0

    # Reports
    try:
        total_reports = db.query(func.count(UserReport.id)).scalar() or 0
        pending_reports = db.query(func.count(UserReport.id)).filter(UserReport.status == "pending").scalar() or 0
    except Exception:
        total_reports = 0
        pending_reports = 0

    # Registration trend (all-time from first registration, grouped by day)
    try:
        reg_rows = (
            db.query(cast(User.created_at, Date), func.count(User.id))
            .group_by(cast(User.created_at, Date))
            .order_by(cast(User.created_at, Date))
            .all()
        )
        daily_registrations = [{"date": str(d), "count": c} for d, c in reg_rows]
    except Exception:
        daily_registrations = []

    # Demographics (STAT-02, STAT-03)
    try:
        users_with_dob = db.query(func.count(User.id)).filter(User.date_of_birth.isnot(None)).scalar() or 0
        age_groups_data = []
        if users_with_dob > 0:
            age_expr = func.date_part("year", func.age(User.date_of_birth))
            age_buckets = db.query(
                case(
                    (age_expr < 25, "18-24"),
                    (age_expr < 35, "25-34"),
                    (age_expr < 45, "35-44"),
                    else_="45+"
                ).label("group"),
                func.count(User.id)
            ).filter(User.date_of_birth.isnot(None)).group_by("group").all()
            for group_name, cnt in age_buckets:
                age_groups_data.append({"group": group_name, "count": cnt, "percentage": round(cnt / users_with_dob * 100, 1)})

        users_with_gender = db.query(func.count(User.id)).filter(User.gender.isnot(None)).scalar() or 0
        gender_data = []
        if users_with_gender > 0:
            gender_rows = db.query(User.gender, func.count(User.id)).filter(User.gender.isnot(None)).group_by(User.gender).all()
            for g, cnt in gender_rows:
                gender_data.append({"gender": g, "count": cnt, "percentage": round(cnt / users_with_gender * 100, 1)})

        demographics = DemographicsOut(
            age_groups=age_groups_data,
            gender_breakdown=gender_data,
            sample_size_dob=users_with_dob,
            sample_size_gender=users_with_gender,
            total_users=total_users,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("demographics query failed: %r", e, exc_info=True)
        demographics = None

    # Group rankings (STAT-06 through STAT-10)
    try:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        # Top 5 by members (STAT-06)
        top_members = db.query(
            GroupMember.group_id, Group.title, func.count(GroupMember.user_id).label("cnt")
        ).join(Group, Group.id == GroupMember.group_id
        ).group_by(GroupMember.group_id, Group.title
        ).order_by(func.count(GroupMember.user_id).desc()
        ).limit(5).all()

        # Trending members - last 30 days (STAT-07)
        trending_members = db.query(
            GroupMember.group_id, Group.title, func.count(GroupMember.user_id).label("cnt")
        ).join(Group, Group.id == GroupMember.group_id
        ).filter(GroupMember.joined_at >= thirty_days_ago
        ).group_by(GroupMember.group_id, Group.title
        ).order_by(func.count(GroupMember.user_id).desc()
        ).limit(5).all()

        # Full ranking (STAT-08) - all groups by member count
        full_ranking = db.query(
            GroupMember.group_id, Group.title, func.count(GroupMember.user_id).label("cnt")
        ).join(Group, Group.id == GroupMember.group_id
        ).group_by(GroupMember.group_id, Group.title
        ).order_by(func.count(GroupMember.user_id).desc()
        ).all()

        # Chat ranking (STAT-09) - by message count
        chat_ranking = db.query(
            GroupMessage.group_id, Group.title, func.count(GroupMessage.id).label("cnt")
        ).join(Group, Group.id == GroupMessage.group_id
        ).group_by(GroupMessage.group_id, Group.title
        ).order_by(func.count(GroupMessage.id).desc()
        ).all()

        # Trending chats - last 30 days (STAT-10)
        trending_chats = db.query(
            GroupMessage.group_id, Group.title, func.count(GroupMessage.id).label("cnt")
        ).join(Group, Group.id == GroupMessage.group_id
        ).filter(GroupMessage.created_at >= thirty_days_ago
        ).group_by(GroupMessage.group_id, Group.title
        ).order_by(func.count(GroupMessage.id).desc()
        ).limit(5).all()

        group_rankings = GroupRankingsOut(
            top_by_members=[{"group_id": r[0], "group_name": r[1], "count": r[2]} for r in top_members],
            trending_members=[{"group_id": r[0], "group_name": r[1], "count": r[2]} for r in trending_members],
            full_ranking=[{"group_id": r[0], "group_name": r[1], "count": r[2]} for r in full_ranking],
            chat_ranking=[{"group_id": r[0], "group_name": r[1], "count": r[2]} for r in chat_ranking],
            trending_chats=[{"group_id": r[0], "group_name": r[1], "count": r[2]} for r in trending_chats],
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("group_rankings query failed: %r", e, exc_info=True)
        group_rankings = None

    return StatsOut(
        total_users=total_users,
        users_by_role=users_by_role,
        role_breakdown=role_breakdown,
        total_groups=total_groups,
        total_sessions=total_sessions,
        total_polls=total_polls,
        top_interests=top_interests,
        total_group_memberships=total_group_memberships,
        avg_members_per_group=avg_members_per_group,
        total_dms=total_dms,
        total_meetings=total_meetings,
        total_qr_scans=total_qr_scans,
        total_agenda_saves=total_agenda_saves,
        avg_points=avg_points,
        max_points=max_points,
        users_with_points=users_with_points,
        total_tickets=total_tickets,
        used_tickets=used_tickets,
        active_tickets=active_tickets,
        pending_reports=pending_reports,
        total_reports=total_reports,
        daily_registrations=daily_registrations,
        demographics=demographics,
        group_rankings=group_rankings,
    )


# ------------------------------------------------------------------
# 6. PUT /admin/theme
# ------------------------------------------------------------------
@router.put("/admin/theme")
def set_theme(
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    preset_id = body.get("preset_id")
    if not preset_id or preset_id not in VALID_THEME_PRESETS:
        raise HTTPException(status_code=400, detail="Invalid theme preset.")
    row = db.get(AppConfig, "theme")
    if row:
        row.value = preset_id
    else:
        db.add(AppConfig(key="theme", value=preset_id))
    log_admin_action(db, admin.id, "set_theme", detail={"preset_id": preset_id})
    db.commit()
    return {"status": "updated", "preset_id": preset_id}


# ------------------------------------------------------------------
# 7. GET /admin/ticket-packages
# ------------------------------------------------------------------
@router.get("/admin/ticket-packages")
def list_ticket_packages(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('ticket_packages')),
):
    packages = db.query(TicketPackage).all()
    return [
        {
            "id": p.id,
            "ref_key": p.ref_key,
            "name": p.name,
            "price_eur": float(p.price_eur),
            "description": p.description,
            "features": p.features or [],
            "stripe_price_id": p.stripe_price_id,
            "max_quantity": p.max_quantity,
            "is_active": p.is_active,
        }
        for p in packages
    ]


# ------------------------------------------------------------------
# 8. POST /admin/ticket-packages
# ------------------------------------------------------------------
@router.post("/admin/ticket-packages")
def create_ticket_package(
    data: TicketPackageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('ticket_packages')),
):
    ref_key = "ticket_" + data.name.lower().replace(" ", "_")
    pkg = TicketPackage(
        ref_key=ref_key,
        name=data.name,
        price_eur=data.price_eur,
        description=data.description,
        features=data.features,
        stripe_price_id=data.stripe_price_id,
        max_quantity=data.max_quantity,
        is_active=data.is_active,
    )
    db.add(pkg)
    log_admin_action(db, current_user.id, "create_ticket_package", target_type="ticket_package", detail={"name": data.name})
    db.commit()
    db.refresh(pkg)
    return {
        "id": pkg.id,
        "ref_key": pkg.ref_key,
        "name": pkg.name,
        "price_eur": float(pkg.price_eur),
        "description": pkg.description,
        "features": pkg.features or [],
        "stripe_price_id": pkg.stripe_price_id,
        "max_quantity": pkg.max_quantity,
        "is_active": pkg.is_active,
    }


# ------------------------------------------------------------------
# 9. PATCH /admin/ticket-packages/{package_id}
# ------------------------------------------------------------------
@router.patch("/admin/ticket-packages/{package_id}")
def update_ticket_package(
    package_id: int,
    data: TicketPackageUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('ticket_packages')),
):
    pkg = db.get(TicketPackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Ticket package not found.")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(pkg, field, value)
    log_admin_action(
        db, current_user.id, "update_ticket_package",
        target_type="ticket_package", target_id=package_id,
        detail=updates,
    )
    db.commit()
    db.refresh(pkg)
    return {
        "id": pkg.id,
        "ref_key": pkg.ref_key,
        "name": pkg.name,
        "price_eur": float(pkg.price_eur),
        "description": pkg.description,
        "features": pkg.features or [],
        "stripe_price_id": pkg.stripe_price_id,
        "max_quantity": pkg.max_quantity,
        "is_active": pkg.is_active,
    }


# ------------------------------------------------------------------
# 10. DELETE /admin/ticket-packages/{package_id}
# ------------------------------------------------------------------
@router.delete("/admin/ticket-packages/{package_id}")
def delete_ticket_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('ticket_packages')),
):
    pkg = db.get(TicketPackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Ticket package not found.")
    log_admin_action(
        db, current_user.id, "delete_ticket_package",
        target_type="ticket_package", target_id=package_id,
        detail={"name": pkg.name},
    )
    db.delete(pkg)
    db.commit()
    return {"status": "deleted"}


# ------------------------------------------------------------------
# 11. GET /admin/audit-log
# ------------------------------------------------------------------
@router.get("/admin/audit-log")
def get_audit_log(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        AuditLogOut(
            id=r.id,
            admin_id=r.admin_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            detail=r.detail,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return {"total": total, "offset": offset, "limit": limit, "items": items}


# ------------------------------------------------------------------
# 12. PUT /admin/config/{key}
# ------------------------------------------------------------------
ALLOWED_CONFIG_KEYS = {
    "theme", "feature_flags", "announcement_banner",
    "schedule_config", "matching_weights", "reward_points",
    "dm_daily_limit", "density_thresholds",
    "experience_levels", "discussion_topics",
    "festival_date_start", "festival_date_end",
    "smart_notif_enabled", "smart_notif_daily_cap",
    "smart_notif_popular_threshold",
    "certificate_template",
    "user_theme_options",
    "app_name", "app_logo_url",
    "wifi_ssid", "wifi_password",
    # Phase 13 Plan 08 — theme customisation slots (THME-01..03)
    "active_theme_preset_id",
    "theme_color_1",
    "theme_color_2",
    "theme_color_3",
    "theme_color_4",
}

# Phase 13 Plan 08 — validation patterns for theme keys.
# Hex values must be 6-digit lowercase/uppercase hex (no shorthand, no alpha).
# Preset ids are short slugs (lowercase, digits, hyphen, underscore).
_THEME_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_PRESET_ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
_THEME_HEX_KEYS = {
    "theme_color_1", "theme_color_2", "theme_color_3", "theme_color_4",
}


@router.put("/admin/config/{key}")
def set_config(
    key: str,
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if key not in ALLOWED_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Config key '{key}' is not allowed.")
    value = body.get("value")
    # Phase 13 Plan 08 — validate theme hex + preset id (T-13-23 mitigation).
    # `null` / None resets the key — no regex check.
    if value is not None:
        if key in _THEME_HEX_KEYS and not _THEME_HEX_RE.match(str(value)):
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be a 6-digit hex color like #abcdef",
            )
        if key == "active_theme_preset_id" and not _PRESET_ID_RE.match(str(value)):
            raise HTTPException(
                status_code=422,
                detail="active_theme_preset_id must be a short lowercase slug "
                "(letters, digits, hyphen, underscore; 1-40 chars)",
            )
    # Apply cascade logic when saving feature flags
    if key == "feature_flags" and isinstance(value, dict):
        value = apply_cascade(value, db)
    row = db.get(AppConfig, key)
    if row:
        row.value = value
    else:
        db.add(AppConfig(key=key, value=value))
    log_admin_action(db, admin.id, "set_config", detail={"key": key, "value": value})
    db.commit()
    return {"key": key, "value": value}


# ------------------------------------------------------------------
# 13. GET /admin/config
# ------------------------------------------------------------------
_CONFIG_DEFAULTS: dict[str, Any] = {
    "schedule_config": {
        "festival_start": "2026-05-20",
        "festival_end": "2026-05-24",
        "slot_start_hour": 9,
        "slot_start_minute": 0,
        "slot_end_hour": 18,
        "slot_end_minute": 0,
        "slot_duration_minutes": 30,
        "meeting_hold_minutes": 120,
    },
    "matching_weights": {
        "max_interest_points": 40,
        "complementary_role_points": 30,
        "same_role_points": 10,
        "points_per_group": 5,
        "max_group_points": 20,
        "points_per_session": 2,
        "max_session_points": 10,
    },
    "reward_points": {
        "ATTEND_SESSION": 50,
        "ONBOARDING": 30,
        "RATE_SESSION": 20,
        "JOIN_GROUP": 20,
        "POLL_VOTE": 10,
        "NETWORKING": 10,
        "GROUP_CHAT": 10,
        "MAP_CHECKIN": 10,
        "QR_SCAN": 10,
    },
    "dm_daily_limit": 50,
    "density_thresholds": {"green": 0.30, "yellow": 0.60, "orange": 0.85},
}

@router.get("/admin/config")
def get_all_config(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = {r.key: r.value for r in db.query(AppConfig).all()}
    result = []
    for key, default in _CONFIG_DEFAULTS.items():
        value = rows.pop(key, None)
        if value is None:
            value = default
        elif isinstance(default, dict) and isinstance(value, dict):
            # Merge: DB values override defaults, but missing keys get defaults
            value = {**default, **value}
        result.append({"key": key, "value": value})
    # Include any remaining DB keys not in defaults
    for key, value in rows.items():
        result.append({"key": key, "value": value})
    return result


# ------------------------------------------------------------------
# 14. GET /admin/feature-registry
# ------------------------------------------------------------------
@router.get("/admin/feature-registry")
def get_feature_registry(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Returns the full feature flag registry with current merged state."""
    merged = get_merged_flags(db)
    return [
        {
            "key": key,
            "label": meta["label"],
            "enabled": merged[key],
            "default": meta["default"],
            "depends_on": meta["depends_on"],
        }
        for key, meta in FEATURE_REGISTRY.items()
    ]


# ------------------------------------------------------------------
# 15. PUT /admin/users/{user_id}/role
# ------------------------------------------------------------------
@router.put("/admin/users/{user_id}/role")
def change_user_role(
    user_id: int,
    data: AdminRoleChangeIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role == data.role:
        raise HTTPException(status_code=400, detail="User already has this role.")
    old_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user.role = data.role
    # Phase 11 D-04/D-12: bump token_version on EVERY role change — promotion or
    # demotion — so previously-issued JWTs for this user are invalidated at the
    # next request via get_current_user's token_version check.
    user.token_version = (user.token_version or 0) + 1
    log_admin_action(
        db, admin.id, "change_role",
        target_type="user", target_id=user_id,
        detail={"old_role": old_role, "new_role": data.role.value},
    )
    db.commit()
    return {"status": "updated", "user_id": user_id, "new_role": data.role.value}


# ------------------------------------------------------------------
# Moderator permissions — admin-only read/write (Phase 11 MODR-02)
# ------------------------------------------------------------------
@router.get("/admin/moderator-permissions", response_model=ModeratorPermissionsOut)
def get_moderator_permissions_endpoint(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.core.moderator_permissions import get_moderator_permissions
    return get_moderator_permissions(db)


@router.put("/admin/moderator-permissions", response_model=ModeratorPermissionsOut)
def update_moderator_permissions_endpoint(
    body: ModeratorPermissionsIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.core.moderator_permissions import (
        get_moderator_permissions,
        set_moderator_permissions,
    )
    old = get_moderator_permissions(db)
    new = set_moderator_permissions(db, body.model_dump())
    log_admin_action(
        db, admin.id, "update_moderator_permissions",
        detail={"old": old, "new": new},
    )
    db.commit()
    return new


# ------------------------------------------------------------------
# 15. GET /admin/reports
# ------------------------------------------------------------------
@router.get("/admin/reports")
def list_reports(
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('user_reports')),
):
    VALID_REPORT_STATUSES = {"pending", "reviewed", "actioned"}
    if status and status not in VALID_REPORT_STATUSES:
        raise HTTPException(400, f"Invalid status. Allowed: {', '.join(VALID_REPORT_STATUSES)}")
    q = db.query(UserReport)
    if status:
        q = q.filter(UserReport.status == status)
    total = q.count()
    reports = q.order_by(UserReport.created_at.desc()).offset(offset).limit(limit).all()
    # Batch-load reporter and reported user names to avoid N+1 queries
    user_ids = set()
    for r in reports:
        user_ids.add(r.reporter_id)
        user_ids.add(r.reported_id)
    users_map = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": r.id,
                "reporter": {"id": r.reporter_id, "name": users_map[r.reporter_id].full_name if r.reporter_id in users_map else None},
                "reported": {"id": r.reported_id, "name": users_map[r.reported_id].full_name if r.reported_id in users_map else None},
                "reason": r.reason,
                "details": r.details,
                "status": r.status,
                "admin_notes": r.admin_notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
    }


class UpdateReportIn(BaseModel):
    status: Literal["pending", "reviewed", "actioned"]
    admin_notes: str | None = Field(None, max_length=2000)


# ------------------------------------------------------------------
# 16. PATCH /admin/reports/{report_id}
# ------------------------------------------------------------------
@router.patch("/admin/reports/{report_id}")
def update_report(
    report_id: int,
    payload: UpdateReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('user_reports')),
):
    report = db.get(UserReport, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    report.status = payload.status
    if payload.admin_notes is not None:
        report.admin_notes = payload.admin_notes
    log_admin_action(db, current_user.id, "update_report", "report", report_id, f"status={payload.status}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------
# Phase 12 — Admin Session Management (D-05, D-09, D-10, D-11)
# ------------------------------------------------------------------

@router.get("/admin/sessions", response_model=list[SessionOut])
def list_admin_sessions(
    search: Optional[str] = None,
    timeframe: str = "upcoming",  # one of "upcoming", "past", "all"
    show_cancelled: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """Admin/moderator session list for Phase 12 admin screen (D-09, D-10).

    Unlike public `GET /program`, this endpoint returns cancelled rows when
    `show_cancelled=true` and applies the `is_cancelled` filter based on the
    query param. Supports search (title ilike) and timeframe segments.
    """
    q = (
        select(ProgramSession)
        .options(
            joinedload(ProgramSession.venue),
            selectinload(ProgramSession.speakers),
        )
        .order_by(ProgramSession.start_time)
    )

    if not show_cancelled:
        q = q.where(ProgramSession.is_cancelled.is_(False))

    now = datetime.now(timezone.utc)
    if timeframe == "upcoming":
        q = q.where(ProgramSession.end_time >= now)
    elif timeframe == "past":
        q = q.where(ProgramSession.end_time < now)
    elif timeframe == "all":
        pass
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid timeframe. Use 'upcoming', 'past', or 'all'.",
        )

    if search:
        like = f"%{search}%"
        q = q.where(ProgramSession.title.ilike(like))

    rows = db.execute(q).unique().scalars().all()
    return [_session_to_out(s) for s in rows]


@router.get("/admin/sessions/{session_id}/impact", response_model=SessionImpactOut)
def get_session_impact(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """Return favorites + chat_messages + qa_items counts for the cancel
    confirmation modal (Phase 12 D-05). Cheap three-SELECT COUNT(*) path."""
    session = db.get(ProgramSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    favorites = db.execute(
        select(func.count()).select_from(UserAgenda).where(UserAgenda.session_id == session_id)
    ).scalar_one()
    chat_messages = db.execute(
        select(func.count()).select_from(SessionChatMessage).where(SessionChatMessage.session_id == session_id)
    ).scalar_one()
    qa_items = db.execute(
        select(func.count()).select_from(SessionQuestion).where(SessionQuestion.session_id == session_id)
    ).scalar_one()

    return SessionImpactOut(
        favorites=favorites,
        chat_messages=chat_messages,
        qa_items=qa_items,
    )


@router.post("/admin/sessions/{session_id}/cancel")
def cancel_session_admin(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """Soft-cancel a session and fan out a push to all favoriters (D-03, D-07, D-08).

    Idempotent: if the session is already cancelled, returns
    {already_cancelled: true, session_id} without sending a second push.
    On first cancellation, sets is_cancelled=true + cancelled_at=now(),
    enqueues push with notif_type='session_reminder' and deeplink
    panathenea://sessions/{session_id}, and writes audit row via
    log_admin_action('cancel_session', ...).
    """
    from app.services.push import send_push_batch

    session = db.get(ProgramSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.is_cancelled:
        # Idempotency guard — preserve original cancelled_at + no double push.
        return {"already_cancelled": True, "session_id": session_id}

    # Flip the flag + stamp timestamp before building the push batch.
    session.is_cancelled = True
    session.cancelled_at = datetime.now(timezone.utc)

    # Capture favoriter user_ids before commit.
    favoriter_ids = db.execute(
        select(UserAgenda.user_id).where(UserAgenda.session_id == session_id)
    ).scalars().all()

    title_copy = "Session cancelled"
    body_copy = f"{session.title} has been cancelled."
    deeplink = f"panathenea://sessions/{session_id}"
    notifications = [
        {
            "user_id": uid,
            "title": title_copy,
            "body": body_copy,
            "notif_type": "session_reminder",
            "ref_id": session_id,
            "deeplink": deeplink,
        }
        for uid in favoriter_ids
    ]
    send_push_batch(db, notifications)

    log_admin_action(
        db,
        current_user.id,
        "cancel_session",
        target_type="session",
        target_id=session_id,
        detail={"favoriters_notified": len(favoriter_ids), "title": session.title},
    )
    db.commit()

    return {
        "already_cancelled": False,
        "session_id": session_id,
        "favoriters_notified": len(favoriter_ids),
    }


@router.post("/admin/sessions/{session_id}/notify-update")
def notify_update_session(
    session_id: int,
    payload: NotifyUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('manage_sessions')),
):
    """Fan out an edit-notification push to favoriters AFTER a PATCH succeeded
    (Phase 12 D-22). Does NOT modify the session — best-effort follow-up.

    Body: {changed_fields: ['time'?, 'venue'?]}. Server validates against the
    whitelist {"time", "venue"} and rejects empty lists with 400.
    """
    from app.services.push import send_push_batch

    session = db.get(ProgramSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Validate changed_fields subset — only 'time' and 'venue' are accepted.
    allowed = {"time", "venue"}
    invalid = [f for f in payload.changed_fields if f not in allowed]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid changed_fields: {invalid}. Allowed: {sorted(allowed)}",
        )
    if not payload.changed_fields:
        raise HTTPException(
            status_code=400,
            detail="changed_fields must be non-empty.",
        )

    favoriter_ids = db.execute(
        select(UserAgenda.user_id).where(UserAgenda.session_id == session_id)
    ).scalars().all()

    # Humanise changed_fields into "time", "venue", or "time and venue"
    # per D-22 copy spec.
    if set(payload.changed_fields) == {"time", "venue"}:
        what = "time and venue"
    elif payload.changed_fields == ["time"]:
        what = "time"
    else:
        what = "venue"

    title_copy = "Session updated"
    body_copy = (
        f"Session '{session.title}' has been updated ({what} changed). "
        "Check the program for details."
    )
    deeplink = f"panathenea://sessions/{session_id}"
    notifications = [
        {
            "user_id": uid,
            "title": title_copy,
            "body": body_copy,
            "notif_type": "session_reminder",
            "ref_id": session_id,
            "deeplink": deeplink,
        }
        for uid in favoriter_ids
    ]
    send_push_batch(db, notifications)

    log_admin_action(
        db,
        current_user.id,
        "notify_update_session",
        target_type="session",
        target_id=session_id,
        detail={
            "changed_fields": payload.changed_fields,
            "favoriters_notified": len(favoriter_ids),
        },
    )
    db.commit()

    return {
        "favoriters_notified": len(favoriter_ids),
        "changed_fields": payload.changed_fields,
    }
