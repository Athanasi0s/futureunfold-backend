"""Tenant-aware Google Wallet EventTicketClass registration.

Creates (or confirms existence of) the two EventTicketClass resources used by
this tenant's wallet passes:

    <GOOGLE_WALLET_ISSUER_ID>.<GOOGLE_WALLET_CLASS_SUFFIX>         -> badge
    <GOOGLE_WALLET_ISSUER_ID>.<GOOGLE_WALLET_TICKET_CLASS_SUFFIX>  -> ticket

Issuer name + event name come from EVENT_NAME (set per-tenant via
`fly secrets set EVENT_NAME=...`). The script is idempotent: if a class with
the computed ID already exists, it prints the existing class and exits 0.

Usage (from festapp-backend repo root, with the tenant's env loaded):
    py -m scripts.register_wallet_classes                   # create BOTH
    py -m scripts.register_wallet_classes --kind badge      # badge only
    py -m scripts.register_wallet_classes --kind ticket     # ticket only

Prerequisites (all set via `fly secrets set -a festapp-api-<slug>` in prod,
or in `.env` locally):

  - TENANT_KEY
  - EVENT_NAME
  - GOOGLE_WALLET_ISSUER_ID                 (shared across tenants)
  - GOOGLE_WALLET_CLASS_SUFFIX              (per-tenant, e.g. "<slug>_badge")
  - GOOGLE_WALLET_TICKET_CLASS_SUFFIX       (per-tenant, e.g. "<slug>_ticket";
                                             defaults to "festapp_ticket")
  - GOOGLE_WALLET_SA_JSON_B64               (shared service account JSON, b64)

Runs once per tenant during provisioning (see scripts/provision_tenant.sh +
docs/ONBOARDING_NEW_TENANT.md). Safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import sys

from googleapiclient.discovery import build
from google.oauth2 import service_account

from app.core import config
from app.services.wallet import _service_account_info, _class_id


# Brand colors — keep stable across tenants for now. If a customer asks for
# their own palette, split these into per-tenant env vars later.
BADGE_HEX = "#194ff0"   # royal blue
TICKET_HEX = "#0ea5e9"  # sky blue


def create_one(client, kind: str) -> None:
    """Create (or confirm existence of) one EventTicketClass for the given kind."""
    class_id = _class_id(kind)
    event_name = config.EVENT_NAME
    issuer_name = event_name  # single brand string covers both fields

    if kind == "badge":
        event_name_value = f"{event_name} Badge"
        hex_bg = BADGE_HEX
    else:
        event_name_value = f"{event_name} Ticket"
        hex_bg = TICKET_HEX

    event_ticket_class = {
        "id": class_id,
        "issuerName": issuer_name,
        "reviewStatus": "UNDER_REVIEW",
        "eventName": {
            "defaultValue": {
                "language": "en-US",
                "value": event_name_value,
            },
        },
        "hexBackgroundColor": hex_bg,
    }

    try:
        existing = client.eventticketclass().get(resourceId=class_id).execute()
        print(f"[{kind}] Class already exists: {class_id}")
        print(json.dumps(existing, indent=2))
        return
    except Exception as e:
        if "404" not in str(e):
            raise

    created = client.eventticketclass().insert(body=event_ticket_class).execute()
    print(f"[{kind}] Class created: {class_id}")
    print(json.dumps(created, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register Google Wallet EventTicketClass resources for the "
                    "current tenant (driven by EVENT_NAME + GOOGLE_WALLET_* env)."
    )
    parser.add_argument(
        "--kind",
        choices=["badge", "ticket", "both"],
        default="both",
        help="Which EventTicketClass to create (default: both). Idempotent.",
    )
    args = parser.parse_args()

    if not config.wallet_configured():
        print(
            "Wallet env vars missing. Set GOOGLE_WALLET_ISSUER_ID, "
            "GOOGLE_WALLET_CLASS_SUFFIX, and GOOGLE_WALLET_SA_JSON_B64 via "
            "`fly secrets set` on the target app first.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Registering classes for tenant '{config.TENANT_KEY}' "
        f"(event name: '{config.EVENT_NAME}', "
        f"issuer: {config.GOOGLE_WALLET_ISSUER_ID})"
    )

    creds = service_account.Credentials.from_service_account_info(
        _service_account_info(),
        scopes=["https://www.googleapis.com/auth/wallet_object.issuer"],
    )
    client = build("walletobjects", "v1", credentials=creds)

    kinds_to_create = ["badge", "ticket"] if args.kind == "both" else [args.kind]
    for k in kinds_to_create:
        create_one(client, k)

    return 0


if __name__ == "__main__":
    sys.exit(main())
