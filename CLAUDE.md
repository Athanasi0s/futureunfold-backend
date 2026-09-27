# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Panathenea — a festival management backend built with FastAPI (Python 3.11+), PostgreSQL, and SQLAlchemy 2.0. Provides APIs for venue/indoor maps, user groups, direct messaging, program sessions, user interests/matching, and JWT authentication.

## Development Commands

### Setup

```bash
docker compose up -d                  # Start PostgreSQL container (port 5442)
cp .env.example .env                  # Create env config
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Database

```bash
alembic upgrade head                              # Run all migrations
alembic revision --autogenerate -m "description"  # Generate migration from model changes
alembic downgrade -1                              # Rollback last migration
```

**Seed scripts** are organised by tenancy under `app/seed/`:

- `app/seed/generic/` — tenant-agnostic defaults shared by every tenant (interests, goals, theme options, ticket packages).
- `app/seed/tenants/<TENANT_KEY>/` — event-specific data (venues, users, groups, sessions, etc.). Panathenea lives under `app/seed/tenants/panathenea/`.

`python -m app.seed.bootstrap` runs the generic seeds then the current tenant's `ordered_seeds` list based on `TENANT_KEY`. It honours `SKIP_SEEDS=1` as an escape hatch.

**Important:** generic seeds are idempotent. Panathenea's tenant seeds (under `app/seed/tenants/panathenea/`) are NOT all idempotent — some insert fresh rows on every run (see `.planning/MULTITENANCY_PLAN.md` Phase A.5 for the audit). Bootstrap is therefore invoked **once** during new-tenant provisioning (via `scripts/provision_tenant.sh`) and NOT wired into `release_command`. Running it manually against an already-seeded DB will inject duplicate test data.

To run an individual seed by path (dev machines only):

```bash
python -m app.seed.generic.seed_interests
python -m app.seed.tenants.panathenea.seed_dummy_map
python -m app.seed.tenants.panathenea.seed_users
# ... etc.
```

### Provisioning a new tenant

```bash
./scripts/provision_tenant.sh <slug> "<Event Name>" <admin_email>
```

End-to-end: creates the Fly app + Postgres, sets `TENANT_KEY` / `JWT_SECRET` / `EVENT_NAME` / `ADMIN_EMAILS` secrets, generates `fly.<slug>.toml`, scaffolds `app/seed/tenants/<slug>/`, appends `<slug>` to `tenants.yml`, first deploy, one-off bootstrap run. ~5–10 min. After it finishes: commit the new files, push to `main`, and add the matching entry in `festapp-mobile/app.config.ts` + `eas.json` + `assets/tenants/<slug>/`.

The full step-by-step onboarding runbook (including the manual platform registrations the script can't automate — OAuth, Firebase, Wallet, Stripe, stores) is in [`docs/ONBOARDING_NEW_TENANT.md`](docs/ONBOARDING_NEW_TENANT.md). Canonical env-var / secret inventory: [`docs/TENANT_DEPENDENCIES.md`](docs/TENANT_DEPENDENCIES.md). See `.planning/MULTITENANCY_PLAN.md` Phase B for plan context.

Helper scripts alongside `provision_tenant.sh`:

- `scripts/verify_tenant.sh <slug>` — smoke-test `/health` + `/config` on a live tenant backend
- `scripts/deprovision_tenant.sh <slug>` — tear down a tenant (destructive, requires typing the slug to confirm; refuses to touch `panathenea`)
- `scripts/register_wallet_classes.py` — tenant-aware Wallet class registration driven by `EVENT_NAME` + `GOOGLE_WALLET_*` env (idempotent)

### Running the Server

```bash
uvicorn app.main:app --reload                                # Dev server (localhost only)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload    # Expose to local network
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
│   ├── routes/          # Endpoint handlers (auth, venues, groups, dm, program, interests, matching)
│   └── schemas.py       # Pydantic request/response models
├── core/
│   ├── config.py        # Env vars: DATABASE_URL, JWT_SECRET
│   ├── security.py      # Bcrypt hashing, JWT create/decode (HS256, 24h expiry)
│   ├── enums.py         # UserRole enum (attendee, speaker, exhibitor, admin)
│   └── deps.py          # FastAPI dependencies: get_db, get_current_user
├── db/
│   ├── session.py       # SQLAlchemy engine & SessionLocal factory
│   └── base.py          # Declarative base
├── models/              # SQLAlchemy ORM models (one file per table)
└── seed/                # Database seeding scripts (idempotent)
```

### Key Patterns

- **Dependency injection**: `Depends(get_db)` for DB sessions, `Depends(get_current_user)` for auth-required endpoints.
- **JWT auth**: Bearer token in `Authorization` header. Token payload contains `sub` (user_id) and `exp`.
- **User roles**: Enum-based roles (attendee, speaker, exhibitor, admin) in `core/enums.py`.
- **Conversation normalization**: DM conversations store user IDs in sorted order (smaller ID = `user_a`) with a unique constraint to ensure one conversation per pair.
- **Rate limiting**: DM endpoint enforces 50 messages/day per user via `_spam_limit_ok()`.
- **GeoJSON in JSONB**: Indoor maps stored as GeoJSON FeatureCollections in `venue_floors.geojson`.
- **Feature keys**: Map features use unique keys like `booth_<venue_key>_F<floor>_<code>` for cross-platform referencing.
- **Cascade deletes**: All foreign keys use `ondelete="CASCADE"`.
- **Timezone-aware timestamps**: All `DateTime` columns use `timezone=True`.
- **Matching algorithm**: Returns top 30 users ranked by common interests count.

### API Route Prefixes

- `/auth` — register, login
- `/me` — current user info, user's groups
- `/venues` — venue list, floors, GeoJSON
- `/groups` — list, join, leave
- `/dm` — send, inbox, conversations, block, report
- `/program` — sessions, speakers, agenda favorites
- `/interests` — list interests, get/set user interests
- `/matching` — get users with common interests
- `/scheduling` — meeting availability, conflicts, locations, meeting CRUD

### Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (default port is 5442 per docker-compose)
- `JWT_SECRET` — HMAC signing key for tokens
- `TENANT_KEY` — multi-tenancy identifier (required; app refuses to boot without it). Local dev uses `panathenea`; production sets per-tenant via `fly secrets set TENANT_KEY=<slug>`. See `.planning/MULTITENANCY_PLAN.md`.

## Conventions

- Snake_case for functions/variables, PascalCase for classes/models
- Greek-language comments appear throughout the codebase
- Error responses use `HTTPException` with standard status codes (400, 401, 403, 404, 429)
- Pydantic schemas enforce API contracts; response models specified on route decorators
- Migrations in `alembic/versions/` — always use `--autogenerate` against current models
