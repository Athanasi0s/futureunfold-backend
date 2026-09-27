from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core import config
from app.core.deps import get_db
from app.core.feature_flags import get_merged_flags
from app.models.app_config import AppConfig

router = APIRouter()


@router.get("/config")
def get_public_config(db: Session = Depends(get_db)):
    """Public endpoint -- no auth required. Returns client-facing configuration."""
    def get_val(key, default=None):
        row = db.get(AppConfig, key)
        return row.value if row else default

    return {
        # Fall back to the tenant's EVENT_NAME (per-tenant Fly secret, set by
        # provision_tenant.sh) when no admin has overridden app_name via the
        # admin panel. Previously hardcoded "Panathenea" leaked that brand into
        # every fresh tenant dashboard (caught on techsaloniki preview 2026-04-21).
        "app_name": get_val("app_name", config.EVENT_NAME),
        "app_logo_url": get_val("app_logo_url", None),
        "theme": get_val("theme", "midnight-indigo"),
        "feature_flags": get_merged_flags(db),
        "announcement_banner": get_val("announcement_banner", None),
        "schedule_config": get_val("schedule_config", {
            "festival_start": "2026-05-20",
            "festival_end": "2026-05-24",
            "slot_start_hour": 9,
            "slot_start_minute": 0,
            "slot_end_hour": 18,
            "slot_end_minute": 0,
            "slot_duration_minutes": 30,
            "meeting_hold_minutes": 120,
        }),
        "matching_weights": get_val("matching_weights", {
            "max_interest_points": 40,
            "complementary_role_points": 30,
            "same_role_points": 10,
            "points_per_group": 5,
            "max_group_points": 20,
            "points_per_session": 2,
            "max_session_points": 10,
        }),
        "density_thresholds": get_val("density_thresholds", {
            "green": 0.30,
            "yellow": 0.60,
            "orange": 0.85,
        }),
        "dm_daily_limit": get_val("dm_daily_limit", 50),
        "reward_points": get_val("reward_points", {
            "ATTEND_SESSION": 50,
            "ONBOARDING": 30,
            "RATE_SESSION": 20,
            "JOIN_GROUP": 20,
            "POLL_VOTE": 10,
            "NETWORKING": 10,
            "GROUP_CHAT": 10,
            "MAP_CHECKIN": 10,
            "QR_SCAN": 10,
        }),
        "user_theme_options": get_val("user_theme_options", []),
        "certificate_template": get_val("certificate_template", {
            "version": 1,
            "festival_name": config.EVENT_NAME,
            "tagline": "Certificate of Attendance",
            "logo_url": None,
            "primary_color": "#194ff0",
            "secondary_color": "#101522",
            "accent_color": "#10b981",
            "background_gradient": ["#101522", "#1a2744"],
            "border_color": "#2a3a6a",
        }),
        "wifi_ssid": get_val("wifi_ssid", None),
        "wifi_password": get_val("wifi_password", None),
        "ai_portraits_url": get_val("ai_portraits_url", None),
        # Phase 13 Plan 08 — theme customisation (THME-01..03).
        # Mobile config-store reads these on launch and passes them to
        # applyThemePreset as overrides. All 5 keys default to None when
        # admin has not set them; mobile falls back to the preset's values.
        "active_theme_preset_id": get_val("active_theme_preset_id", None),
        "theme_color_1": get_val("theme_color_1", None),
        "theme_color_2": get_val("theme_color_2", None),
        "theme_color_3": get_val("theme_color_3", None),
        "theme_color_4": get_val("theme_color_4", None),
    }
