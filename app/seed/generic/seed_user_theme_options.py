"""
Seed the user_theme_options AppConfig key with all available theme preset IDs.
Idempotent — skips if already set.
"""
from app.db.session import SessionLocal
from app.models.app_config import AppConfig

THEME_IDS = [
    "midnight-indigo",
    "sunset-coral",
    "deep-ocean",
    "royal-purple",
    "forest-emerald",
    "warm-amber",
    "nordic-frost",
    "cherry-blossom",
    "festival-fire",
    "cosmic-night",
    "electric-blue",
    "athens-sunrise",
    "classic-mono",
]


def seed():
    db = SessionLocal()
    try:
        existing = db.get(AppConfig, "user_theme_options")
        if existing:
            print("user_theme_options already set, skipping")
            return
        config = AppConfig(key="user_theme_options", value=THEME_IDS)
        db.add(config)
        db.commit()
        print("Seeded user_theme_options with %d themes" % len(THEME_IDS))
    finally:
        db.close()


run = seed

if __name__ == "__main__":
    run()
