from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import DATABASE_URL

# Engine = η "μηχανή" που μιλάει με τη βάση.
# Τα pool/timeout kwargs είναι PostgreSQL-specific — το SQLite (που χρησιμοποιείται
# από το test suite του Phase 13) τα απορρίπτει με TypeError. Διακλαδώνουμε στο URL
# ώστε η ίδια διαδρομή import να σηκώνει και production Postgres και in-memory SQLite.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=3,
        max_overflow=2,
        connect_args={"connect_timeout": 10},
    )

# SessionLocal = το αντικείμενο που θα χρησιμοποιούμε σε κάθε API call για queries
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
