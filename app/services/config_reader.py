from sqlalchemy.orm import Session
from app.models.app_config import AppConfig


def get_config_value(db: Session, key: str, default=None):
    """Query AppConfig table, return value or default."""
    row = db.get(AppConfig, key)
    return row.value if row else default
