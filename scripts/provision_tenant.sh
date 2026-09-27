#!/usr/bin/env bash
# Provisions a new tenant for FestApp:
#   - Fly app + attached Postgres cluster
#   - fly.<slug>.toml config generated from fly.panathenea.toml
#   - Per-tenant secrets (TENANT_KEY, JWT_SECRET, EVENT_NAME, ADMIN_EMAILS)
#   - app/seed/tenants/<slug>/ scaffold (empty ordered_seeds)
#   - Append slug to tenants.yml
#   - First deploy + one-off bootstrap run (generic seed defaults only)
#
# Usage:
#   scripts/provision_tenant.sh <slug> "<event name>" <admin email>
#
# Example:
#   scripts/provision_tenant.sh acmeconf "ACME Conf 2026" admin@acmeconf.com
#
# Must be run from the festapp-backend repo root. Requires `flyctl auth login`
# already completed and `openssl` on PATH.
#
# !!! MUST BE RUN IN A REAL INTERACTIVE TERMINAL (NOT CI, NOT A TOOL THAT
# !!! CAN'T ANSWER STDIN PROMPTS). Two interactive gates:
#
#   1. This script's own `read -p "Continue? [y/N]"` (line ~108).
#
#   2. `flyctl postgres create` (step [3/9]) prompts twice and there is NO
#      non-interactive flag combo that silences both:
#        - "Unmanaged Fly Postgres is not supported... Use Managed Postgres?"
#          → answer NO to stay on unmanaged (consistent with existing tenants).
#        - "Select VM size:" → pick `shared-cpu-1x:256MB` to match
#          techsaloniki / reworks (cheapest tier; bump later if needed).
#
# If the script bails partway through step [3/9], the Fly app + fly.<slug>.toml
# already exist. To recover, either:
#   (a) destroy the app + delete the toml and re-run cleanly:
#         flyctl apps destroy festapp-api-<slug>
#         rm fly.<slug>.toml
#   (b) resume manually from `flyctl postgres create` onward — all subsequent
#       commands in this script are non-interactive (attach takes --yes; secrets,
#       deploy, ssh-bootstrap are all safe to invoke directly).
#
# Admin emails: this script accepts ONE email and validates it as a single
# address. ADMIN_EMAILS itself is comma-separated. For multiple admins, run
# the script with one, then patch:
#   flyctl secrets set -a festapp-api-<slug> ADMIN_EMAILS="a@x.com,b@x.com"
#
# After the script finishes:
#   1. Commit fly.<slug>.toml, app/seed/tenants/<slug>/, tenants.yml
#   2. Push to master → CI matrix will deploy this tenant on every future push
#   3. Add matching entry to festapp-mobile/app.config.ts + eas.json + assets/

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <slug> \"<event name>\" <admin email>"
    echo ""
    echo "Example:"
    echo "  $0 acmeconf \"ACME Conf 2026\" admin@acmeconf.com"
    exit 1
fi

SLUG="$1"
EVENT_NAME="$2"
ADMIN_EMAIL="$3"

APP_NAME="festapp-api-${SLUG}"
DB_NAME="festapp-api-${SLUG}-db"
FLY_TOML="fly.${SLUG}.toml"
SEED_DIR="app/seed/tenants/${SLUG}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

if [[ ! "$SLUG" =~ ^[a-z][a-z0-9]*$ ]]; then
    echo "ERROR: slug must be lowercase alphanumeric starting with a letter (got: '$SLUG')"
    exit 1
fi

if [[ ! "$ADMIN_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "ERROR: admin email looks invalid (got: '$ADMIN_EMAIL')"
    exit 1
fi

if [[ ! -f "fly.panathenea.toml" ]]; then
    echo "ERROR: run this from the festapp-backend repo root (fly.panathenea.toml not found)"
    exit 1
fi

if [[ -f "$FLY_TOML" ]]; then
    echo "ERROR: $FLY_TOML already exists — tenant may already be provisioned"
    exit 1
fi

if [[ -d "$SEED_DIR" ]]; then
    echo "ERROR: $SEED_DIR already exists — tenant may already be provisioned"
    exit 1
fi

if grep -Eq "^[[:space:]]*-[[:space:]]*${SLUG}[[:space:]]*$" tenants.yml 2>/dev/null; then
    echo "ERROR: '$SLUG' already listed in tenants.yml"
    exit 1
fi

command -v flyctl >/dev/null || { echo "ERROR: flyctl not on PATH"; exit 1; }
command -v openssl >/dev/null || { echo "ERROR: openssl not on PATH"; exit 1; }

if ! flyctl auth whoami >/dev/null 2>&1; then
    echo "ERROR: not logged into flyctl. Run 'flyctl auth login' first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

cat <<EOF
About to provision a new tenant:

  Slug         : $SLUG
  Event name   : $EVENT_NAME
  Admin email  : $ADMIN_EMAIL
  Fly app      : $APP_NAME
  Postgres     : $DB_NAME
  Backend URL  : https://${APP_NAME}.fly.dev

This creates billable Fly.io resources (app + Postgres cluster) and modifies
local files (fly.${SLUG}.toml, ${SEED_DIR}/, tenants.yml).

EOF

read -p "Continue? [y/N] " -n 1 -r
echo ""
if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Generate fly.<slug>.toml from the panathenea template
# ---------------------------------------------------------------------------

echo ""
echo "[1/9] Writing $FLY_TOML..."
sed "s|^app = \"festapp-api-panathenea\"$|app = \"${APP_NAME}\"|" fly.panathenea.toml > "$FLY_TOML"
grep -q "^app = \"${APP_NAME}\"$" "$FLY_TOML" || {
    echo "ERROR: sed failed to rewrite the app name"
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Create the Fly app
# ---------------------------------------------------------------------------

echo ""
echo "[2/9] Creating Fly app '$APP_NAME'..."
flyctl apps create "$APP_NAME" --org personal

# ---------------------------------------------------------------------------
# 3. Create + attach Postgres
# ---------------------------------------------------------------------------

echo ""
echo "[3/9] Creating Postgres cluster '$DB_NAME' (takes 2-3 min)..."
flyctl postgres create \
    --name "$DB_NAME" \
    --region fra \
    --initial-cluster-size 1 \
    --volume-size 3

echo ""
echo "      Attaching Postgres to app..."
flyctl postgres attach "$DB_NAME" -a "$APP_NAME" --yes

# ---------------------------------------------------------------------------
# 4. Set secrets (must be set BEFORE first deploy — TENANT_KEY is required at boot)
# ---------------------------------------------------------------------------

echo ""
echo "[4/9] Setting app secrets..."
JWT_SECRET="$(openssl rand -hex 32)"
flyctl secrets set -a "$APP_NAME" \
    TENANT_KEY="$SLUG" \
    JWT_SECRET="$JWT_SECRET" \
    EVENT_NAME="$EVENT_NAME" \
    ADMIN_EMAILS="$ADMIN_EMAIL"

# ---------------------------------------------------------------------------
# 5. Scaffold the tenant's seed folder
# ---------------------------------------------------------------------------

echo ""
echo "[5/9] Scaffolding $SEED_DIR..."
mkdir -p "$SEED_DIR"

cat > "$SEED_DIR/__init__.py" <<PYEOF
"""${SLUG} tenant seed order. Run via app/seed/bootstrap.py.

ordered_seeds is empty by default — generic defaults (interests, goals,
theme options, ticket packages) are still applied at bootstrap. Add
tenant-specific seeds (venues, users, groups, sessions, etc.) here as the
customer's content becomes available.
"""

ordered_seeds: list = []
PYEOF

cat > "$SEED_DIR/README.md" <<MDEOF
# ${EVENT_NAME} — tenant seed scripts

This folder holds event-specific seed scripts for the \`${SLUG}\` tenant.

Each seed module must export a \`run\` callable. Add the callable to
\`ordered_seeds\` in \`__init__.py\` to include it in the bootstrap order.

Generic defaults (interests / goals / theme options / ticket packages) come
from \`app/seed/generic/\` and are always applied before these.

Seed scripts MUST be idempotent — they are re-runnable via
\`python -m app.seed.bootstrap\`. See \`app/seed/tenants/panathenea/\` for
reference implementations (note: panathenea's scripts are legacy and not fully
idempotent; new tenants should do better).
MDEOF

# ---------------------------------------------------------------------------
# 6. Append slug to tenants.yml
# ---------------------------------------------------------------------------

echo ""
echo "[6/9] Appending '$SLUG' to tenants.yml..."
echo "  - $SLUG" >> tenants.yml

# ---------------------------------------------------------------------------
# 7. First deploy — builds image, runs alembic upgrade head via release_command
# ---------------------------------------------------------------------------

echo ""
echo "[7/9] First deploy (builds Docker image + runs alembic upgrade head)..."
flyctl deploy -c "$FLY_TOML"

# ---------------------------------------------------------------------------
# 8. Health check
# ---------------------------------------------------------------------------

echo ""
echo "[8/9] Verifying /health..."
HEALTH_URL="https://${APP_NAME}.fly.dev/health"
# Retry up to 6 times (60s total) — machines need a moment after first boot.
for attempt in 1 2 3 4 5 6; do
    if curl -fsS -o /dev/null --max-time 10 "$HEALTH_URL"; then
        echo "      /health returned 200"
        break
    fi
    if [[ $attempt -eq 6 ]]; then
        echo "ERROR: /health did not return 200 after 60s. Check 'flyctl logs -a $APP_NAME'."
        exit 1
    fi
    echo "      attempt $attempt failed, retrying..."
    sleep 10
done

# ---------------------------------------------------------------------------
# 9. One-off bootstrap — populates generic seed defaults (first deploy only)
# ---------------------------------------------------------------------------

echo ""
echo "[9/9] Running python -m app.seed.bootstrap (generic defaults; tenant-specific seeds are empty by design)..."
flyctl ssh console -a "$APP_NAME" -C "python -m app.seed.bootstrap"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

cat <<EOF

============================================================
Tenant '$SLUG' provisioned successfully.

  Backend      : https://${APP_NAME}.fly.dev
  Health       : ${HEALTH_URL}
  Admin email  : ${ADMIN_EMAIL}
  Postgres     : ${DB_NAME}

Next steps:

  1. Review and commit the new/modified files locally:
       ${FLY_TOML}
       ${SEED_DIR}/
       tenants.yml
     Then push to master. CI matrix will include this tenant in every
     future deploy.

  2. In festapp-mobile, add a '${SLUG}' entry:
       - app.config.ts          (tenant map)
       - eas.json               (${SLUG}-development / preview / production profiles)
       - assets/tenants/${SLUG}/   (icon, splash, favicon, google-services.json)

  3. Admin first login: the admin user must register via the mobile app
     using '${ADMIN_EMAIL}' and select role 'admin'. ADMIN_EMAILS is set
     on Fly so the registration will be accepted.

  4. Once event-specific content (venues, groups, sessions, etc.) is ready,
     add seed modules to ${SEED_DIR}/ and register them in ordered_seeds.
============================================================
EOF
