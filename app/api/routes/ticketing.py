"""
Ticketing endpoints:
- GET  /tickets/packages        → list active packages (TICK-01, TICK-07)
- POST /tickets/checkout        → create Stripe Checkout session (TICK-02)
- GET  /tickets/me              → my tickets with QR codes (TICK-03)
- POST /webhooks/stripe         → Stripe webhook — creates ticket on payment (TICK-08, TICK-09)
- POST /tickets/validate        → admin: scan QR → mark used (TICK-05, TICK-06, INFR-01)
- GET  /tickets/payment-complete  → success page for Stripe redirect
- GET  /tickets/payment-cancelled → cancel page for Stripe redirect
"""
import uuid
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, EVENT_NAME
from app.core.deps import get_db, get_current_user, require_admin, require_feature, require_moderator_scope
from app.models.user import User
from app.models.ticket_package import TicketPackage
from app.models.ticket import Ticket, TicketStatus
from app.api.schemas import (
    TicketPackageOut, CheckoutIn, CheckoutOut,
    TicketOut, TicketValidateIn, TicketValidateOut,
)
from app.services.email import send_ticket_confirmation

router = APIRouter(dependencies=[require_feature("tickets")])

# Separate ungated router for webhooks — Stripe must always reach us,
# even when the "tickets" feature flag is disabled (otherwise paid tickets
# are never confirmed).
webhook_router = APIRouter()
logger = logging.getLogger(__name__)

stripe.api_key = STRIPE_SECRET_KEY


# ──────────────────────────────────────────────────────────────────
# GET /tickets/packages — list active packages (TICK-01, TICK-07)
# ──────────────────────────────────────────────────────────────────
@router.get("/tickets/packages", response_model=list[TicketPackageOut])
def get_ticket_packages(db: Session = Depends(get_db)):
    """Returns only is_active=True packages. No auth required (browsable before purchase)."""
    packages = (
        db.query(TicketPackage)
        .filter(TicketPackage.is_active == True)
        .order_by(TicketPackage.price_eur.asc())
        .all()
    )
    return [
        TicketPackageOut(
            id=p.id,
            ref_key=p.ref_key,
            name=p.name,
            price_eur=float(p.price_eur),
            description=p.description,
            features=p.features or [],
            max_quantity=p.max_quantity,
        )
        for p in packages
    ]


# ──────────────────────────────────────────────────────────────────
# POST /tickets/checkout — create Stripe Checkout session (TICK-02)
# ──────────────────────────────────────────────────────────────────
@router.post("/tickets/checkout", response_model=CheckoutOut)
def create_checkout(
    payload: CheckoutIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a Stripe Checkout session and returns the URL. Mobile opens via expo-web-browser."""
    pkg = db.query(TicketPackage).filter(
        TicketPackage.id == payload.package_id,
        TicketPackage.is_active == True,
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Ticket package not found or inactive.")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment not configured.")

    # Build success/cancel URLs — simple backend HTML pages (no custom scheme redirect)
    base = "https://festapp-api-panathenea.fly.dev"
    success_url = f"{base}/tickets/payment-complete"
    cancel_url = f"{base}/tickets/payment-cancelled"

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": pkg.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": str(current_user.id),
            "package_id": str(pkg.id),
        },
        client_reference_id=str(current_user.id),
    )
    return CheckoutOut(checkout_url=session.url)


# ──────────────────────────────────────────────────────────────────
# GET /tickets/me — my tickets with QR codes (TICK-03)
# ──────────────────────────────────────────────────────────────────
@router.get("/tickets/me", response_model=list[TicketOut])
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all tickets for the current user, newest first."""
    tickets = (
        db.query(Ticket)
        .filter(Ticket.user_id == current_user.id)
        .order_by(Ticket.created_at.desc())
        .all()
    )
    return [
        TicketOut(
            id=t.id,
            package_id=t.package_id,
            package_name=t.package.name if t.package else "Unknown",
            qr_code=t.qr_code,
            status=t.status.value,
            created_at=t.created_at.isoformat(),
        )
        for t in tickets
    ]


# ──────────────────────────────────────────────────────────────────
# POST /webhooks/stripe — Stripe webhook (TICK-08, TICK-09)
# CRITICAL: No auth dependency. No Pydantic body param. Raw body MUST
# be read before signature verification.
# ──────────────────────────────────────────────────────────────────
@webhook_router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()   # MUST be first — before any JSON parsing

    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=stripe_signature,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        _handle_checkout_completed(db, event["data"]["object"])

    return {"status": "ok"}


def _handle_checkout_completed(db: Session, session: dict) -> None:
    """
    Creates a ticket after successful payment.
    Idempotent: checks stripe_payment_intent_id before inserting (TICK-08).
    Sends confirmation email — fails silently if SendGrid not configured (TICK-04).
    """
    payment_intent_id = session.get("payment_intent") or session.get("id")
    user_id = int(session["metadata"]["user_id"])
    package_id = int(session["metadata"]["package_id"])
    logger.info(f"Webhook: checkout completed — user={user_id}, package={package_id}, pi={payment_intent_id}")

    # Idempotency check — TICK-08
    existing = db.query(Ticket).filter(
        Ticket.stripe_payment_intent_id == payment_intent_id
    ).first()
    if existing:
        return  # Already processed — duplicate webhook, do nothing

    qr_code = str(uuid.uuid4())

    ticket = Ticket(
        user_id=user_id,
        package_id=package_id,
        stripe_payment_intent_id=payment_intent_id,
        qr_code=qr_code,
        status=TicketStatus.active,
    )
    db.add(ticket)
    try:
        db.commit()
        db.refresh(ticket)
    except Exception as e:
        logger.error(f"Ticket creation failed: {e}")
        db.rollback()
        return

    # Send confirmation email — fail silently if not configured (TICK-04)
    try:
        user = ticket.user
        package = ticket.package
        send_ticket_confirmation(
            to_email=user.email,
            buyer_name=user.full_name or user.email,
            package_name=package.name,
            qr_uuid=qr_code,
            purchase_date=ticket.created_at.strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.error(f"Ticket email failed for ticket {ticket.id}: {e}")


# ──────────────────────────────────────────────────────────────────
# POST /tickets/validate — admin scans QR (TICK-05, TICK-06, INFR-01)
# ──────────────────────────────────────────────────────────────────
@router.post("/tickets/validate", response_model=TicketValidateOut)
def validate_ticket(
    payload: TicketValidateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_moderator_scope('validate_ticket')),
):
    """Admin/moderator(validate_ticket): validate a ticket QR code. Marks as used. Final — cannot be un-marked."""
    ticket = db.query(Ticket).filter(Ticket.qr_code == payload.qr_code).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Invalid QR code — ticket not found.")
    if ticket.status == TicketStatus.used:
        raise HTTPException(status_code=409, detail="Ticket already used.")
    if ticket.status == TicketStatus.cancelled:
        raise HTTPException(status_code=410, detail="Ticket is cancelled.")

    ticket.status = TicketStatus.used
    db.commit()
    db.refresh(ticket)

    return TicketValidateOut(
        ticket_id=ticket.id,
        buyer_name=ticket.user.full_name or ticket.user.email,
        package_name=ticket.package.name,
        purchased_at=ticket.created_at.isoformat(),
        status="valid",
    )


# ──────────────────────────────────────────────────────────────────
# Success / Cancel redirect pages
# ──────────────────────────────────────────────────────────────────
@router.get("/tickets/payment-complete", response_class=HTMLResponse)
def payment_complete():
    return HTMLResponse(content="""
    <html><body style="font-family:sans-serif;text-align:center;padding:60px">
      <h2>Payment Complete</h2>
      <p>Your ticket has been confirmed. Return to the {EVENT_NAME} app to view your ticket.</p>
    </body></html>
    """)

@router.get("/tickets/payment-cancelled", response_class=HTMLResponse)
def payment_cancelled():
    return HTMLResponse(content="""
    <html><body style="font-family:sans-serif;text-align:center;padding:60px">
      <h2>Payment Cancelled</h2>
      <p>No charge was made. Return to the {EVENT_NAME} app to try again.</p>
    </body></html>
    """)
