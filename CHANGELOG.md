# Changelog

## 2026-03-12 — Production Stability Fixes: OOM Kills & Google Calendar (Round 2)

### Problem

Despite earlier fixes (see 2026-03-12 Round 1 below), the backend continued experiencing **OOM kills every ~20 minutes** and Google Calendar busy times were intermittently missing.

### Root Cause Analysis

Three new issues identified from Fly.io production logs:

1. **`fly.staging.toml` had `memory = "256mb"`** — The CI/CD deploy uses `fly.staging.toml`, which reset machines to 256MB on every deploy, undoing any manual `fly scale memory` changes.

2. **Google Calendar `build()` with `cache_discovery=False`** — Every API call re-downloaded and re-parsed the ~200KB discovery document. The `/scheduling/availability/` endpoint calls this 2x per request (once per user), adding significant memory churn.

3. **Unbounded SQLAlchemy connection pool** — No explicit `pool_size` or `max_overflow` allowed unbounded connection growth on a single-worker setup.

### Fixes Applied

| Fix | Change | Impact |
|-----|--------|--------|
| Scale machines to 512MB | `fly.staging.toml` → `memory = "512mb"` + manual `fly scale memory 512` | Doubled memory headroom, prevents OOM kills across deploys |
| Use static discovery doc | `build("calendar", "v3", static_discovery=True)` | Uses bundled discovery doc from pip package — zero network calls, zero parsing overhead |
| Cap connection pool | `pool_size=3, max_overflow=2` on SQLAlchemy engine | Caps total connections at 5, appropriate for single Gunicorn worker |

### Files Changed

- `fly.staging.toml` — memory 256mb → 512mb
- `app/services/google_calendar.py` — `static_discovery=True`
- `app/db/session.py` — `pool_size=3, max_overflow=2`

### Verification

After deploy, production logs confirmed:
- No OOM kills or worker timeouts
- Google Calendar busy times returned successfully (`Got 2 busy ranges for user 25`)

---

## 2026-03-12 — Database Connection Resilience & OAuth Timeout (Round 1)

### Problem

502 errors caused by stale database connections after Fly.io auto-stops the Postgres machine, and Gunicorn worker hangs when Google's OAuth token endpoint is slow.

### Fixes Applied

| Fix | Change | Impact |
|-----|--------|--------|
| Connection pool recycling | Added `pool_recycle=300` to SQLAlchemy engine | Proactively closes connections older than 5 minutes, preventing stale connections after DB auto-stop |
| Connection timeout | Added `connect_args={"connect_timeout": 10}` | Prevents workers from blocking indefinitely when Postgres is waking up |
| Gunicorn timeout increase | `--timeout 120 --graceful-timeout 30` in Dockerfile (was 60s) | Gives DB more time to wake from auto-stop before killing workers |
| OAuth token refresh timeout | Added 10s timeout to Google token refresh request | Prevents worker hang if Google's token endpoint is slow/unreachable |

### Files Changed

- `Dockerfile` — Gunicorn timeout 60s → 120s, added graceful-timeout 30s
- `app/db/session.py` — `pool_recycle=300`, `connect_timeout=10`
- `app/services/google_calendar.py` — 10s timeout on token refresh

---

## 2026-03-10 — Google Calendar Integration Fixes

### Problem

Google Calendar integration had multiple issues: worker crashes from hanging API calls, busy times appearing shifted by 3 hours (timezone mismatch), and no visibility into API behavior for debugging.

### Fixes Applied

| Fix | Change | Impact |
|-----|--------|--------|
| HTTP timeout on Google API calls | Added 10s timeout via `httplib2.Http(timeout=10)` + `AuthorizedHttp` | Prevents worker crashes from hanging Google API calls |
| Batch freebusy queries | Fetch busy times for entire festival range in 2 API calls (one per user) instead of 10 (one per day per user) | Reduced API calls from 10 to 2 per availability request |
| Timezone conversion | Convert Google freebusy results from real UTC to Europe/Athens local time, then store as UTC to match scheduling grid convention | Fixed 3-hour shift in busy time display |
| Logging & debugging | Added structured logging for credential building, busy ranges (raw + converted), and freebusy errors | Enabled production debugging of calendar issues |

### Files Changed

- `app/services/google_calendar.py` — timeout, timezone fix, batching, logging
- `app/api/routes/scheduling.py` — pre-fetch gcal busy times for full festival range
- `app/main.py` — logging configuration
