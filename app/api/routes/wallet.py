"""Google Wallet pass-issuance API (Phase 13 — GWLT-01, kinded for gap 5b).

POST /me/wallet/pass/{kind} returns a signed Save-to-Wallet URL for the
authenticated user.

kind="badge"  → badge pass (QR = str(user.id), deterministic object ID per user)
kind="ticket" → per-ticket pass; requires ticket_id in body. Backend fetches the
                Ticket row, verifies ownership (T-13-GAP-10-01), and embeds
                ticket.qr_code (UUID) as the barcode — matching the value the
                venue scanner reads via POST /tickets/validate.

Legacy route: POST /me/wallet/pass (no kind) — grace alias for badge, kept one
release cycle while mobile clients roll out. Safe to remove once all clients
are on 13-10+ build.

Ο χρήστης πατάει "Add to Google Wallet" στο mobile → κάνει POST εδώ → παίρνει πίσω
ένα URL της μορφής https://pay.google.com/gp/v/save/<signed_jwt>, το οποίο ανοίγει
με Linking.openURL και το Google Wallet app εμφανίζει το pass.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.app_config import AppConfig
from app.models.ticket import Ticket
from app.services.wallet import (
    build_save_url,
    WalletNotConfiguredError,
    EMPTY_CREDENTIALS_ERROR,
)
from app.api.schemas import WalletPassIn, WalletPassOut

router = APIRouter()

WalletPassKind = Literal["badge", "ticket"]


def _resolve_logo_url(db: Session) -> str | None:
    """Χρησιμοποιούμε το certificate logo (Phase 10) ως logo για το Wallet pass.

    Εάν δεν έχει οριστεί, επιστρέφουμε None και το pass δεν θα έχει logo — το
    build_event_ticket_object το αποδέχεται.

    Τυλίγουμε σε try/except επειδή το app_config table χρησιμοποιεί JSONB (PostgreSQL)
    και σε περιβάλλοντα test/SQLite ή πριν την πρώτη migration μπορεί να λείπει·
    σε αυτήν την περίπτωση απλώς παραλείπουμε το logo αντί να σκάσει το endpoint.
    """
    try:
        row = db.query(AppConfig).filter(AppConfig.key == "certificate_template").first()
    except Exception:
        return None
    if row and isinstance(row.value, dict) and row.value.get("logo_url"):
        return row.value["logo_url"]
    return None


def _issue_pass(
    kind: WalletPassKind,
    ticket_id: int | None,
    db: Session,
    user: User,
) -> WalletPassOut:
    """Core pass-issuance logic, shared by kinded and legacy routes.

    For kind="ticket":
      - ticket_id is required (400 if missing)
      - Ticket row fetched and ownership verified (404 if not found or not owned)
      - Barcode value = ticket.qr_code (UUID the venue scanner reads)
        CRITICAL: NOT str(ticket_id) — the validate endpoint uses qr_code,
        not ticket.id, so encoding the wrong value would make wallet-pass
        scans fail while in-app TicketQRModal scans (which render ticket.qr_code)
        succeed. This distinction closes gap 5b.

    For kind="badge":
      - Barcode value = str(user.id) — matches DigitalIdCard.tsx convention
    """
    if kind == "ticket":
        if ticket_id is None:
            raise HTTPException(
                status_code=400,
                detail="ticket_id is required when kind='ticket'",
            )
        # Combined ownership check: identical 404 for not-found AND not-owned
        # to prevent ticket-existence enumeration (T-13-GAP-10-01).
        ticket = db.get(Ticket, ticket_id)
        if not ticket or ticket.user_id != user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
        # CRITICAL: barcode MUST carry ticket.qr_code (the UUID) so that a wallet-pass
        # scan reaches the same code path as an in-app TicketQRModal scan.
        # ticketing.py:226: `Ticket.qr_code == payload.qr_code` is the validate query.
        qr_value = ticket.qr_code
    else:  # badge
        qr_value = str(user.id)
        ticket_id = None  # normalise for badge path

    full_name = user.full_name or user.email or f"Attendee #{user.id}"
    logo_url = _resolve_logo_url(db)
    try:
        save_url = build_save_url(
            kind=kind,
            user_id=user.id,
            full_name=full_name,
            qr_value=qr_value,
            ticket_id=ticket_id,
            logo_url=logo_url,
        )
    except WalletNotConfiguredError:
        raise HTTPException(status_code=503, detail=EMPTY_CREDENTIALS_ERROR)
    return WalletPassOut(save_url=save_url)


@router.post("/me/wallet/pass/{kind}", response_model=WalletPassOut)
def create_wallet_pass_kinded(
    kind: WalletPassKind,
    body: WalletPassIn = WalletPassIn(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WalletPassOut:
    """Kinded wallet pass — POST /me/wallet/pass/badge or /me/wallet/pass/ticket."""
    return _issue_pass(kind, body.ticket_id, db, user)


# Legacy alias — kept one release cycle while mobile rolls out. Default: badge.
@router.post("/me/wallet/pass", response_model=WalletPassOut)
def create_wallet_pass_legacy(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WalletPassOut:
    """Legacy alias for POST /me/wallet/pass/badge (backward compat)."""
    return _issue_pass("badge", None, db, user)
