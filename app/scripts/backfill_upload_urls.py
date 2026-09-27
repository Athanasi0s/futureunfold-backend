"""One-off backfill: prefix relative /uploads/ paths with PUBLIC_BASE_URL.

History: POST /upload used to return a relative `/uploads/<file>` path, which
the mobile client stored directly into avatar_url / cover_url / image_url /
app_config.value fields. React Native's <Image source={{ uri }}> cannot load
relative URLs, so any such row renders as a broken/placeholder image. The
endpoint now returns absolute URLs; this script heals existing rows.

Idempotent — rows that already hold absolute URLs (or are NULL) are skipped.
Safe to re-run any number of times.

Run per tenant (the prefix is derived from each tenant's PUBLIC_BASE_URL):

    flyctl ssh console -a festapp-api-<slug> -C "python -m app.scripts.backfill_upload_urls"
"""

from sqlalchemy.orm import Session

from app.core.config import PUBLIC_BASE_URL
from app.db.session import SessionLocal
from app.models.app_config import AppConfig
from app.models.exhibitor_staff import ExhibitorStaff
from app.models.session import Session as SessionModel
from app.models.user import User
from app.models.venue import Venue

PREFIX = f"{PUBLIC_BASE_URL}"


def _needs_fix(value):
    return isinstance(value, str) and value.startswith("/uploads/")


def _backfill_column(db: Session, label: str, model, column_name: str) -> int:
    """Find rows where the named column starts with /uploads/ and prefix them."""
    column = getattr(model, column_name)
    rows = db.query(model).filter(column.like("/uploads/%")).all()
    count = 0
    for row in rows:
        old = getattr(row, column_name)
        if not _needs_fix(old):
            continue
        setattr(row, column_name, f"{PREFIX}{old}")
        count += 1
    if count:
        db.commit()
    print(f"  {label}: {count} rows updated")
    return count


def _backfill_app_config(db: Session) -> int:
    """Heal app_config rows holding upload URLs.

    Two shapes to handle:
      - app_logo_url: top-level string value (`"/uploads/..."`).
      - certificate_template: nested JSON; the `logo_url` field may be relative.
    """
    count = 0

    # app_logo_url — value is a bare JSON string
    row = db.query(AppConfig).filter(AppConfig.key == "app_logo_url").one_or_none()
    if row is not None and _needs_fix(row.value):
        row.value = f"{PREFIX}{row.value}"
        count += 1
        print(f"  app_config[app_logo_url]: prefixed")

    # certificate_template.logo_url — nested in a JSON object
    row = db.query(AppConfig).filter(AppConfig.key == "certificate_template").one_or_none()
    if row is not None and isinstance(row.value, dict):
        nested = row.value.get("logo_url")
        if _needs_fix(nested):
            # Reassign the dict so SQLAlchemy detects the change on a JSONB column.
            new_value = {**row.value, "logo_url": f"{PREFIX}{nested}"}
            row.value = new_value
            count += 1
            print(f"  app_config[certificate_template].logo_url: prefixed")

    if count:
        db.commit()
    print(f"  app_config total: {count} fields updated")
    return count


def main() -> None:
    print(f"Backfilling /uploads/ URLs with prefix: {PREFIX}")
    db = SessionLocal()
    try:
        total = 0
        total += _backfill_column(db, "users.avatar_url", User, "avatar_url")
        total += _backfill_column(db, "users.cover_url", User, "cover_url")
        total += _backfill_column(db, "venues.avatar_url", Venue, "avatar_url")
        total += _backfill_column(
            db, "exhibitor_staff.avatar_url", ExhibitorStaff, "avatar_url"
        )
        total += _backfill_column(
            db, "sessions.image_url", SessionModel, "image_url"
        )
        total += _backfill_app_config(db)
        print(f"\nDone. {total} fields updated overall.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
