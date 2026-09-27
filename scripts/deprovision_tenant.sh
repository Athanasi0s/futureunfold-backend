#!/usr/bin/env bash
# Tears down a tenant previously created by scripts/provision_tenant.sh.
#
# Destroys the Fly app + attached Postgres cluster, removes the
# fly.<slug>.toml config, strips <slug> from tenants.yml, and deletes
# app/seed/tenants/<slug>/.
#
# Usage:
#   scripts/deprovision_tenant.sh <slug>
#
# Example:
#   scripts/deprovision_tenant.sh acmeconf
#
# What it does NOT do (manual clean-up outside this repo):
#   - Revoke Google Cloud OAuth clients created for this tenant
#   - Delete the tenant's Firebase project
#   - Delete the tenant's Apple App Store Connect / Google Play app records
#   - Unregister any Google Wallet classes (no delete API; harmless to leave)
#   - Unregister Stripe webhooks (customer-owned)
#   - Remove the tenant entry from festapp-mobile/app.config.ts + eas.json
#
# Meant for tearing down TEST tenants. Running this against a live customer
# backend is DESTRUCTIVE and IRREVERSIBLE (Postgres data is lost).

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <slug>"
    echo ""
    echo "Example:"
    echo "  $0 acmeconf"
    exit 1
fi

SLUG="$1"

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

if [[ "$SLUG" == "panathenea" ]]; then
    echo "ERROR: refusing to deprovision 'panathenea' — this is the production tenant."
    echo "       If you really mean this, do it manually step by step."
    exit 1
fi

if [[ ! -f "tenants.yml" ]]; then
    echo "ERROR: run this from the festapp-backend repo root (tenants.yml not found)"
    exit 1
fi

command -v flyctl >/dev/null || { echo "ERROR: flyctl not on PATH"; exit 1; }

if ! flyctl auth whoami >/dev/null 2>&1; then
    echo "ERROR: not logged into flyctl. Run 'flyctl auth login' first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

cat <<EOF
About to DEPROVISION tenant '$SLUG':

  Fly app (destroy)      : $APP_NAME
  Postgres (destroy)     : $DB_NAME
  Fly config (delete)    : $FLY_TOML
  Seed folder (delete)   : $SEED_DIR
  tenants.yml entry      : '- ${SLUG}'   (will be removed)

THIS IS IRREVERSIBLE. All Postgres data for this tenant will be lost.

EOF

read -p "Type the slug '$SLUG' to confirm: " CONFIRM
if [[ "$CONFIRM" != "$SLUG" ]]; then
    echo "Aborted (slug did not match)."
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Destroy the Fly app (also detaches Postgres attachment)
# ---------------------------------------------------------------------------

echo ""
echo "[1/5] Destroying Fly app '$APP_NAME'..."
if flyctl apps list --json 2>/dev/null | grep -q "\"Name\":[[:space:]]*\"${APP_NAME}\""; then
    flyctl apps destroy "$APP_NAME" --yes
else
    echo "      App '$APP_NAME' not found on Fly — skipping."
fi

# ---------------------------------------------------------------------------
# 2. Destroy the Postgres cluster
# ---------------------------------------------------------------------------

echo ""
echo "[2/5] Destroying Postgres cluster '$DB_NAME'..."
if flyctl apps list --json 2>/dev/null | grep -q "\"Name\":[[:space:]]*\"${DB_NAME}\""; then
    flyctl apps destroy "$DB_NAME" --yes
else
    echo "      Postgres cluster '$DB_NAME' not found on Fly — skipping."
fi

# ---------------------------------------------------------------------------
# 3. Remove fly.<slug>.toml
# ---------------------------------------------------------------------------

echo ""
echo "[3/5] Removing $FLY_TOML..."
if [[ -f "$FLY_TOML" ]]; then
    rm -f "$FLY_TOML"
    echo "      Removed."
else
    echo "      Not present — skipping."
fi

# ---------------------------------------------------------------------------
# 4. Strip slug from tenants.yml
# ---------------------------------------------------------------------------

echo ""
echo "[4/5] Stripping '- $SLUG' from tenants.yml..."
if grep -Eq "^[[:space:]]*-[[:space:]]*${SLUG}[[:space:]]*$" tenants.yml; then
    # Portable in-place delete (works on BSD + GNU sed)
    tmp="$(mktemp)"
    grep -Ev "^[[:space:]]*-[[:space:]]*${SLUG}[[:space:]]*$" tenants.yml > "$tmp"
    mv "$tmp" tenants.yml
    echo "      Removed."
else
    echo "      Entry not present — skipping."
fi

# ---------------------------------------------------------------------------
# 5. Remove seed folder
# ---------------------------------------------------------------------------

echo ""
echo "[5/5] Removing $SEED_DIR..."
if [[ -d "$SEED_DIR" ]]; then
    rm -rf "$SEED_DIR"
    echo "      Removed."
else
    echo "      Not present — skipping."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

cat <<EOF

============================================================
Tenant '$SLUG' deprovisioned.

Remaining manual clean-up (outside this repo):

  1. festapp-mobile/app.config.ts      — remove '$SLUG' entry
  2. festapp-mobile/eas.json           — remove '${SLUG}-*' profiles
  3. festapp-mobile/assets/tenants/$SLUG/ — delete
  4. Google Cloud OAuth clients        — revoke tenant's clients
  5. Firebase project                  — delete (if dedicated)
  6. Apple App Store Connect app       — delete (if submitted)
  7. Google Play Console app           — delete (if submitted)

Commit the backend changes and push to master:

  git rm fly.${SLUG}.toml app/seed/tenants/${SLUG}
  git add tenants.yml
  git commit -m "chore: deprovision tenant ${SLUG}"
  git push

The CI matrix will stop deploying this tenant on the next push.
============================================================
EOF
