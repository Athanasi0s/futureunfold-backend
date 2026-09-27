"""
Email service for ticket confirmation.
Uses SendGrid with inline QR code attachment (cid: reference — NOT data: URL).
Fails silently if SENDGRID_API_KEY is not configured (logs the error).
"""
import logging
import base64
from io import BytesIO

import qrcode
import qrcode.constants
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileType,
    FileName, Disposition, ContentId
)

from app.core.config import SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, EVENT_NAME

logger = logging.getLogger(__name__)


def generate_qr_base64(data: str) -> str:
    """Generate QR code PNG as base64 string. Used for email inline attachment."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def send_ticket_confirmation(
    to_email: str,
    buyer_name: str,
    package_name: str,
    qr_uuid: str,
    purchase_date: str,
) -> None:
    """
    Send ticket confirmation email with embedded QR code.
    Uses cid: inline attachment — required for Gmail/Outlook compatibility.
    Raises an exception if SendGrid is not configured (caller must handle silently).
    """
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not configured")

    qr_base64 = generate_qr_base64(qr_uuid)

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1a1a2e;">{EVENT_NAME} — Your Ticket</h2>
      <p>Hi {buyer_name},</p>
      <p>Your ticket has been confirmed. Show this QR code at the entrance.</p>
      <table style="margin: 24px 0;">
        <tr><td><strong>Ticket Type:</strong></td><td>{package_name}</td></tr>
        <tr><td><strong>Purchase Date:</strong></td><td>{purchase_date}</td></tr>
      </table>
      <div style="text-align: center; margin: 32px 0;">
        <img src="cid:ticket_qr" width="200" height="200" alt="Ticket QR Code" />
      </div>
      <p style="color: #666; font-size: 12px;">
        This QR code is unique to your ticket. Do not share it.
      </p>
    </div>
    """

    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=to_email,
        subject=f"Your Ticket — {EVENT_NAME}",
        html_content=html_content,
    )

    attachment = Attachment(
        FileContent(qr_base64),
        FileName("ticket_qr.png"),
        FileType("image/png"),
        Disposition("inline"),
        ContentId("ticket_qr"),   # matches cid:ticket_qr in HTML
    )
    message.attachment = attachment

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)
