"""
Google Calendar Integration API routes.

Endpoints:
- POST /auth/google/callback     - Exchange OAuth code for tokens
- GET  /me/google-calendar       - Get connection status
- DELETE /me/google-calendar     - Disconnect Google Calendar
"""

from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, get_user_from_token
from app.core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from app.services.token_encryption import encrypt_token, decrypt_token
from app.services.google_calendar import (
    store_google_tokens,
    get_google_tokens,
    delete_google_tokens,
)
from app.models.user import User
from app.api.schemas import GoogleCallbackIn, GoogleCalendarStatusOut

import json
import base64
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
REDIRECT_URI_SELF = None  # Computed at request time


def _success_html(message: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Success</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#111;color:#fff;
text-align:center}}h1{{font-size:1.5em}}</style></head>
<body><div><h1>{message}</h1><p>You can close this window and return to the app.</p>
</div></body></html>"""


def _error_html(message: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#111;color:#f66;
text-align:center}}h1{{font-size:1.5em}}</style></head>
<body><div><h1>{message}</h1><p>Please close this window and try again.</p>
</div></body></html>"""


@router.get("/auth/google/redirect")
def google_oauth_redirect(request: Request, db: Session = Depends(get_db)):
    """
    Receive Google OAuth callback, exchange code for tokens, store them,
    and show a success/error page. The mobile app polls for status after
    the browser is closed.
    """
    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state", "")

    if not code:
        return HTMLResponse(content=_error_html("Authorization failed — no code received."))

    # Decode state: contains code_verifier and JWT
    try:
        state_json = base64.b64decode(encoded_state).decode("utf-8")
        state_data = json.loads(state_json)
        code_verifier = state_data["cv"]
        jwt_token = state_data["jwt"]
    except Exception:
        return HTMLResponse(content=_error_html("Invalid state parameter."))

    # Identify user from JWT
    try:
        user = get_user_from_token(jwt_token, db)
    except Exception:
        return HTMLResponse(content=_error_html("Authentication expired. Please log in again."))

    # Exchange code for tokens — use the same redirect_uri the mobile sent to Google
    redirect_uri = str(request.url_for("google_oauth_redirect"))
    # Fly.io sits behind a proxy, so url_for may return http:// — force https
    redirect_uri = redirect_uri.replace("http://", "https://")
    with httpx.Client() as client:
        resp = client.post(
            GOOGLE_TOKEN_URI,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )

    if resp.status_code != 200:
        logger.error("Google token exchange failed: %s", resp.text)
        return HTMLResponse(content=_error_html("Token exchange failed. Please try again."))

    tokens = resp.json()

    if "refresh_token" not in tokens:
        return HTMLResponse(content=_error_html("No refresh token received. Please try again."))

    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

    store_google_tokens(
        db=db,
        user_id=user.id,
        access_token=encrypt_token(tokens["access_token"]),
        refresh_token=encrypt_token(tokens["refresh_token"]),
        token_expiry=token_expiry,
    )

    return HTMLResponse(content=_success_html("Google Calendar connected!"))


@router.post("/auth/google/callback")
def google_callback(
    data: GoogleCallbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exchange Google OAuth authorization code for tokens and store them."""
    with httpx.Client() as client:
        resp = client.post(
            GOOGLE_TOKEN_URI,
            data={
                "code": data.code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": data.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": data.code_verifier,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    tokens = resp.json()

    if "refresh_token" not in tokens:
        raise HTTPException(
            status_code=400,
            detail="No refresh token. Please re-authorize with consent prompt.",
        )

    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

    store_google_tokens(
        db=db,
        user_id=current_user.id,
        access_token=encrypt_token(tokens["access_token"]),
        refresh_token=encrypt_token(tokens["refresh_token"]),
        token_expiry=token_expiry,
    )

    return {"connected": True}


@router.get("/me/google-calendar", response_model=GoogleCalendarStatusOut)
def get_google_calendar_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Google Calendar connection status."""
    record = get_google_tokens(db, current_user.id)
    if not record:
        return GoogleCalendarStatusOut(connected=False)
    return GoogleCalendarStatusOut(connected=True, is_valid=record.is_valid)


@router.delete("/me/google-calendar")
def disconnect_google_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnect Google Calendar and revoke tokens."""
    record = get_google_tokens(db, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")

    # Best-effort revocation at Google
    try:
        with httpx.Client() as client:
            client.post(
                GOOGLE_REVOKE_URI,
                params={"token": decrypt_token(record.refresh_token)},
            )
    except Exception:
        pass

    delete_google_tokens(db, current_user.id)
    return {"connected": False}
