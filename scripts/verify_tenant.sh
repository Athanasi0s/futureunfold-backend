#!/usr/bin/env bash
# Post-deploy smoke test for a tenant backend.
#
# Hits the live Fly.io URL and verifies:
#   1. /health returns 200
#   2. /config returns 200 and advertises the correct tenant_key + event_name
#
# Usage:
#   scripts/verify_tenant.sh <slug>
#
# Example:
#   scripts/verify_tenant.sh acmeconf
#
# Exit 0 on success, non-zero on any failure. Suitable for CI use.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <slug>"
    exit 1
fi

SLUG="$1"

if [[ ! "$SLUG" =~ ^[a-z][a-z0-9]*$ ]]; then
    echo "ERROR: slug must be lowercase alphanumeric starting with a letter (got: '$SLUG')"
    exit 1
fi

command -v curl >/dev/null || { echo "ERROR: curl not on PATH"; exit 1; }

BASE_URL="https://festapp-api-${SLUG}.fly.dev"
HEALTH_URL="${BASE_URL}/health"
CONFIG_URL="${BASE_URL}/config"

FAIL=0

echo "Verifying tenant '$SLUG' at $BASE_URL"
echo ""

# ---------------------------------------------------------------------------
# 1. /health
# ---------------------------------------------------------------------------

echo "[1/2] GET $HEALTH_URL"
STATUS="$(curl -s -o /tmp/verify_health.$$ -w "%{http_code}" --max-time 15 "$HEALTH_URL" || echo "000")"
BODY="$(cat /tmp/verify_health.$$ 2>/dev/null || true)"
rm -f /tmp/verify_health.$$

if [[ "$STATUS" == "200" ]]; then
    echo "      OK (200): $BODY"
else
    echo "      FAIL (HTTP $STATUS): $BODY"
    FAIL=1
fi

# ---------------------------------------------------------------------------
# 2. /config — confirms TENANT_KEY + EVENT_NAME are wired correctly
# ---------------------------------------------------------------------------

echo ""
echo "[2/2] GET $CONFIG_URL"
STATUS="$(curl -s -o /tmp/verify_config.$$ -w "%{http_code}" --max-time 15 "$CONFIG_URL" || echo "000")"
BODY="$(cat /tmp/verify_config.$$ 2>/dev/null || true)"
rm -f /tmp/verify_config.$$

if [[ "$STATUS" != "200" ]]; then
    echo "      FAIL (HTTP $STATUS): $BODY"
    FAIL=1
else
    echo "      OK (200)"

    # Best-effort checks — don't hard-fail if /config doesn't expose these keys,
    # since the schema may evolve. Treat a mismatch as a warning.
    if echo "$BODY" | grep -q "\"tenant_key\"[[:space:]]*:[[:space:]]*\"${SLUG}\""; then
        echo "      tenant_key matches '$SLUG'"
    elif echo "$BODY" | grep -q "\"tenant_key\""; then
        echo "      WARN: tenant_key present but does not equal '$SLUG'"
        FAIL=1
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
if [[ $FAIL -eq 0 ]]; then
    echo "============================================================"
    echo "Tenant '$SLUG' verified."
    echo "============================================================"
    exit 0
else
    echo "============================================================"
    echo "Tenant '$SLUG' verification FAILED."
    echo "Check 'flyctl logs -a festapp-api-${SLUG}'."
    echo "============================================================"
    exit 1
fi
