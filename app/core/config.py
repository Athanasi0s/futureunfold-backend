import os
from dotenv import load_dotenv

# Φορτώνουμε μεταβλητές από αρχείο .env (αν υπάρχει)
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://panathenea:panathenea@localhost:5442/panathenea",
)

# `fly postgres attach` emits a DATABASE_URL with the `postgres://` scheme,
# which SQLAlchemy 2.0 rejects ("NoSuchModuleError: Can't load plugin:
# sqlalchemy.dialects:postgres"). Rewrite to the driver-qualified scheme at
# import so every future `provision_tenant.sh` run works without a manual
# `fly secrets set DATABASE_URL=...` override (Phase E follow-up #1).
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+psycopg2://", 1
    )

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")

# Multi-tenancy: identifies which tenant this deployment serves. Drives seed folder
# selection (app/seed/tenants/<TENANT_KEY>/) and is surfaced on a few admin endpoints.
# Must be set — set via `fly secrets set TENANT_KEY=<slug>` in production, or in
# `.env` locally. Failing loudly at import prevents accidental cross-tenant deploys.
TENANT_KEY = os.getenv("TENANT_KEY")
if not TENANT_KEY:
    raise RuntimeError(
        "TENANT_KEY env var is required. "
        "Set it in .env (local dev) or via `fly secrets set TENANT_KEY=<slug>` (production)."
    )

# Absolute base URL of this backend, used to turn paths returned by /upload
# into URLs React Native's <Image source={{ uri }}> can actually load.
# Defaults to the Fly host pattern; override in local dev via
# `PUBLIC_BASE_URL=http://localhost:8000` in .env.
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    f"https://festapp-api-{TENANT_KEY}.fly.dev",
).rstrip("/")

# Directory where uploaded files are stored and served from /uploads.
# Local dev defaults to a project-relative writable folder instead of /data,
# because /data is read-only on macOS.
UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "./data/uploads"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_TOKEN_ENCRYPTION_KEY = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "noreply@example.com")
EVENT_NAME = os.getenv("EVENT_NAME", "Panathenea Festival")

# EVENTORA one-time invitation links. The shared secret must be exchanged
# through an approved secret-management channel and never committed.
EVENTORA_MAGIC_LINK_SECRET = os.getenv("EVENTORA_MAGIC_LINK_SECRET", "")
EVENTORA_MAGIC_LINK_ISSUER = os.getenv("EVENTORA_MAGIC_LINK_ISSUER", "eventora")
EVENTORA_MAGIC_LINK_AUDIENCE = os.getenv(
    "EVENTORA_MAGIC_LINK_AUDIENCE", "future-unfold-app"
)

ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

# ------------------------------------------------------------------
# Google Wallet (Phase 13 — GWLT-01)
# ------------------------------------------------------------------
# All three values must be set via `fly secrets set` before the wallet
# endpoint is exercised end-to-end. Missing values at import time are
# tolerated — the service module raises a clear error at call time only.

GOOGLE_WALLET_ISSUER_ID: str | None = os.environ.get("GOOGLE_WALLET_ISSUER_ID")
GOOGLE_WALLET_CLASS_SUFFIX: str | None = os.environ.get("GOOGLE_WALLET_CLASS_SUFFIX")
# Ticket-kind class suffix — separate from the badge class so both badge and
# per-ticket passes can coexist in the same Google Wallet without "already added" collision.
# Default "festapp_ticket" is safe to bake in; the badge suffix remains env-driven
# because it was historically configured that way before this plan.
GOOGLE_WALLET_TICKET_CLASS_SUFFIX: str | None = os.environ.get(
    "GOOGLE_WALLET_TICKET_CLASS_SUFFIX", "festapp_ticket"
)
GOOGLE_WALLET_SA_JSON_B64: str | None = os.environ.get("GOOGLE_WALLET_SA_JSON_B64")
# Origin(s) that may open save links in Wallet; used as the JWT `origins` claim.
# Matches the deployed app URL; include the Fly.io staging URL for dev builds.
GOOGLE_WALLET_ORIGIN: str = os.environ.get(
    "GOOGLE_WALLET_ORIGIN",
    "https://festapp-api-panathenea.fly.dev",
)


def wallet_configured() -> bool:
    """Returns True iff all three wallet secrets are present at call time."""
    return all([
        GOOGLE_WALLET_ISSUER_ID,
        GOOGLE_WALLET_CLASS_SUFFIX,
        GOOGLE_WALLET_SA_JSON_B64,
    ])
