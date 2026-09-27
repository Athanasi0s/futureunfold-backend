from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String, primary_key=True)
    value = Column(JSONB, nullable=False)
