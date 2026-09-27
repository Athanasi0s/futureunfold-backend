"""Google Wallet pass-issuance service (Phase 13 — GWLT-01, kinded in gap 5b).

Responsible for signing a Save-to-Wallet JWT on the server. Never accept
the service account JSON via HTTP; it MUST be loaded from Fly.io secrets
only (env var GOOGLE_WALLET_SA_JSON_B64).

Ο υπογραφέας χρησιμοποιεί το google.auth.crypt.RSASigner — δεν κάνουμε
hand-roll PEM parsing, ώστε να αποφύγουμε λάθη που θα δημιουργούσαν μη
επαληθεύσιμα JWTs στη μεριά του Google (βλ. RESEARCH §Pitfall 1).

Phase 13 gap 5b: build_save_url and build_event_ticket_object now accept a
`kind` parameter ("badge" | "ticket"). Each kind uses a distinct
EventTicketClass and distinct object ID format:
  badge  -> <ISSUER>.festapp_badge_<user_id>           (backward-compatible)
  ticket -> <ISSUER>.festapp_ticket_<user_id>_<ticket_id>  (new, per-ticket)
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Any, Literal

from google.auth import crypt, jwt

from app.core import config


class WalletNotConfiguredError(RuntimeError):
    """Raised when any of the three GOOGLE_WALLET_* env vars is missing."""


EMPTY_CREDENTIALS_ERROR = (
    "Google Wallet is not configured on this environment. "
    "Ensure GOOGLE_WALLET_ISSUER_ID, GOOGLE_WALLET_CLASS_SUFFIX, and "
    "GOOGLE_WALLET_SA_JSON_B64 are set via `fly secrets set` on the target app."
)

WalletPassKind = Literal["badge", "ticket"]


@lru_cache(maxsize=1)
def _service_account_info() -> dict:
    """Decode + parse the base64-encoded service account JSON exactly once."""
    if not config.GOOGLE_WALLET_SA_JSON_B64:
        raise WalletNotConfiguredError(EMPTY_CREDENTIALS_ERROR)
    raw = base64.b64decode(config.GOOGLE_WALLET_SA_JSON_B64)
    return json.loads(raw)


@lru_cache(maxsize=1)
def _signer() -> crypt.RSASigner:
    """Cache the RSASigner at module level — parsing the PEM is expensive."""
    info = _service_account_info()
    return crypt.RSASigner.from_service_account_info(info)


def _class_suffix_for(kind: WalletPassKind) -> str:
    """Return the EventTicketClass suffix for the given kind."""
    if kind == "badge":
        suffix = config.GOOGLE_WALLET_CLASS_SUFFIX
    elif kind == "ticket":
        suffix = config.GOOGLE_WALLET_TICKET_CLASS_SUFFIX
    else:
        raise ValueError(f"Unknown WalletPassKind: {kind!r}")
    if not suffix:
        raise WalletNotConfiguredError(EMPTY_CREDENTIALS_ERROR)
    return suffix


def _class_id(kind: WalletPassKind) -> str:
    """Return the fully-qualified EventTicketClass ID for the given kind."""
    if not config.GOOGLE_WALLET_ISSUER_ID:
        raise WalletNotConfiguredError(EMPTY_CREDENTIALS_ERROR)
    return f"{config.GOOGLE_WALLET_ISSUER_ID}.{_class_suffix_for(kind)}"


def _object_id(kind: WalletPassKind, user_id: int, ticket_id: int | None = None) -> str:
    """Return the deterministic wallet object ID.

    Badge:  <classId>_<user_id>           — preserves existing IDs (no user churn)
    Ticket: <classId>_<user_id>_<ticket_id> — distinct per ticket (gap-5b)
    """
    base = f"{_class_id(kind)}_{user_id}"
    if kind == "ticket":
        if ticket_id is None:
            raise ValueError("ticket_id is required when kind='ticket'")
        return f"{base}_{ticket_id}"
    return base


def build_event_ticket_object(
    kind: WalletPassKind,
    user_id: int,
    full_name: str,
    qr_value: str,
    ticket_id: int | None = None,
    logo_url: str | None = None,
) -> dict[str, Any]:
    """Build the EventTicketObject payload for a single user's pass.

    Φτιάχνει το object JSON που αποστέλλεται μέσα στο JWT payload. Τα IDs είναι
    deterministic ώστε επαναλαμβανόμενες αιτήσεις να μη δημιουργούν duplicates
    — το Google Wallet κάνει merge με βάση το `id`.

    kind="badge"  → object id = <ISSUER>.festapp_badge_<user_id>  (backward compat)
    kind="ticket" → object id = <ISSUER>.festapp_ticket_<user_id>_<ticket_id>
    """
    obj: dict[str, Any] = {
        "id": _object_id(kind, user_id, ticket_id),
        "classId": _class_id(kind),
        "state": "ACTIVE",
        "ticketHolderName": full_name,
        "barcode": {"type": "QR_CODE", "value": qr_value},
    }
    if logo_url:
        obj["logo"] = {"sourceUri": {"uri": logo_url}}
    return obj


def build_save_url(
    kind: WalletPassKind,
    user_id: int,
    full_name: str,
    qr_value: str,
    ticket_id: int | None = None,
    logo_url: str | None = None,
) -> str:
    """Sign a Save-to-Wallet JWT and return the public save URL.

    Επιστρέφει https://pay.google.com/gp/v/save/<signed_jwt>. Ο client απλώς
    καλεί Linking.openURL με αυτό το URL — ποτέ δεν βλέπει το private key.

    kind="badge"  → badge pass (QR = str(user.id) by convention)
    kind="ticket" → per-ticket pass (QR = ticket.qr_code UUID, looked up server-side)
    """
    if not config.wallet_configured():
        raise WalletNotConfiguredError(EMPTY_CREDENTIALS_ERROR)

    sa_info = _service_account_info()
    obj = build_event_ticket_object(kind, user_id, full_name, qr_value, ticket_id, logo_url)

    claims = {
        "iss": sa_info["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "origins": [config.GOOGLE_WALLET_ORIGIN],
        "payload": {
            "eventTicketObjects": [obj],
        },
    }
    token_bytes = jwt.encode(_signer(), claims)
    token = token_bytes.decode("utf-8")
    return f"https://pay.google.com/gp/v/save/{token}"
