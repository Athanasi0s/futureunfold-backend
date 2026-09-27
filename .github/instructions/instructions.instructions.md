---
applyTo: '**'
---
## Project Overview

Panathenea — a festival management backend built with FastAPI (Python 3.11+), PostgreSQL, and SQLAlchemy 2.0. Provides APIs for venue/indoor maps, user groups, direct messaging, and JWT authentication.

## Development Commands

### Setup

```bash
docker compose up -d                  # Start PostgreSQL container
cp .env.example .env                  # Create env config
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Database

```bash
alembic upgrade head                              # Run all migrations
alembic revision --autogenerate -m "description"  # Generate migration from model changes
alembic downgrade -1                              # Rollback last migration
python -m app.seed.seed_dummy_map                 # Seed venues, floors, test users, groups
python -m app.seed.seed_groups                    # Seed additional groups (idempotent)
```

### Running the Server

```bash
uvicorn app.main:app --reload         # Dev server at http://127.0.0.1:8000
```

- Swagger docs: `http://127.0.0.1:8000/docs`
- Health check: `GET /health`

### Tests

No test framework is currently configured.

## Architecture

```
app/
├── main.py              # FastAPI app, CORS, health endpoint, router inclusion
├── api/
│   ├── router.py        # Aggregates all sub-routers
│   ├── routes/          # Endpoint handlers (auth, venues, groups, dm)
│   └── schemas.py       # Pydantic request/response models
├── core/
│   ├── config.py        # Env vars: DATABASE_URL, JWT_SECRET
│   ├── security.py      # Bcrypt hashing, JWT create/decode (HS256, 24h expiry)
│   └── deps.py          # FastAPI dependencies: get_db, get_current_user
├── db/
│   ├── session.py       # SQLAlchemy engine & SessionLocal factory
│   └── base.py          # Declarative base
├── models/              # SQLAlchemy ORM models (one file per table)
└── seed/                # Database seeding scripts
```

### Key Patterns

- **Dependency injection**: `Depends(get_db)` for DB sessions, `Depends(get_current_user)` for auth-required endpoints.
- **JWT auth**: Bearer token in `Authorization` header. Token payload contains `sub` (user_id) and `exp`.
- **Conversation normalization**: DM conversations store user IDs in sorted order (smaller ID = `user_a`) with a unique constraint to ensure one conversation per pair.
- **Rate limiting**: DM endpoint enforces 50 messages/day per user via `_spam_limit_ok()`.
- **GeoJSON in JSONB**: Indoor maps stored as GeoJSON FeatureCollections in `venue_floors.geojson`.
- **Feature keys**: Map features use unique keys like `booth_<venue_key>_F<floor>_<code>` for cross-platform referencing.
- **Cascade deletes**: All foreign keys use `ondelete="CASCADE"`.
- **Timezone-aware timestamps**: All `DateTime` columns use `timezone=True`.

### API Route Prefixes

- `/auth` — register, login
- `/me` — current user info, user's groups
- `/venues` — venue list, floors, GeoJSON
- `/groups` — list, join, leave
- `/dm` — send, inbox, conversations, block, report

### Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (default: `postgresql+psycopg2://panathenea:panathenea@localhost:5432/panathenea`)
- `JWT_SECRET` — HMAC signing key for tokens

## Conventions

- Snake_case for functions/variables, PascalCase for classes/models
- Greek-language comments appear throughout the codebase
- Error responses use `HTTPException` with standard status codes (400, 401, 403, 404, 429)
- Pydantic schemas enforce API contracts; response models specified on route decorators
- Migrations in `alembic/versions/` — always use `--autogenerate` against current models
