from app.db.session import SessionLocal
from app.models.app_config import AppConfig


VALUES = {
    "app_name": "FUTURE UNFOLD",
    "theme": "future-unfold",
    "active_theme_preset_id": "future-unfold",
    "ai_portraits_url": "https://gtfutureunfold.gr",
    "schedule_config": {
        "festival_start": "2026-11-24",
        "festival_end": "2026-11-24",
        "slot_start_hour": 18,
        "slot_start_minute": 0,
        "slot_end_hour": 21,
        "slot_end_minute": 30,
        "slot_duration_minutes": 15,
        "meeting_hold_minutes": 120,
    },
    "feature_flags": {
        "schedule": True,
        "map": False,
        "digital_id": True,
        "networking": False,
        "groups": False,
        "group_chat": False,
        "direct_messages": False,
        "rewards": False,
        "leaderboard": False,
        "certificates": False,
        "tickets": False,
        "polls": False,
        "exhibitors": True,
        "exhibitor_chat": False,
        "session_chat": False,
        "session_qa": False,
        "location_sharing": False,
        "density": False,
        "notifications": True,
        "recommendations": False,
        "scheduling": False,
        "festival_stats": False,
    },
}


def run() -> None:
    db = SessionLocal()
    try:
        for key, value in VALUES.items():
            row = db.get(AppConfig, key)
            if row is None:
                db.add(AppConfig(key=key, value=value))
            else:
                row.value = value
        db.commit()
        print("Future Unfold app configuration seeded")
    finally:
        db.close()
