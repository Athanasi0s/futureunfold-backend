import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from google_auth_httplib2 import AuthorizedHttp
import httplib2
from sqlalchemy.orm import Session

from app.core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from app.services.token_encryption import encrypt_token, decrypt_token
from app.models.google_calendar_token import GoogleCalendarToken

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Timeout for Google API calls (seconds)
GOOGLE_API_TIMEOUT = 10

# Festival timezone — Google freebusy results are returned in this timezone
# so they align with the scheduling grid (which stores "wall clock" times as UTC).
FESTIVAL_TIMEZONE = "Europe/Athens"


def store_google_tokens(
    db: Session,
    user_id: int,
    access_token: str,
    refresh_token: str,
    token_expiry: datetime | None,
) -> GoogleCalendarToken:
    """Upsert Google Calendar tokens for a user."""
    record = db.query(GoogleCalendarToken).filter(
        GoogleCalendarToken.user_id == user_id
    ).first()

    if record:
        record.access_token = access_token
        record.refresh_token = refresh_token
        record.token_expiry = token_expiry
        record.is_valid = True
    else:
        record = GoogleCalendarToken(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            is_valid=True,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    return record


def get_google_tokens(db: Session, user_id: int) -> GoogleCalendarToken | None:
    """Get Google Calendar token record for a user."""
    return db.query(GoogleCalendarToken).filter(
        GoogleCalendarToken.user_id == user_id
    ).first()


def mark_google_token_invalid(db: Session, user_id: int) -> None:
    """Mark a user's Google Calendar token as invalid."""
    record = db.query(GoogleCalendarToken).filter(
        GoogleCalendarToken.user_id == user_id
    ).first()
    if record:
        record.is_valid = False
        db.commit()


def delete_google_tokens(db: Session, user_id: int) -> None:
    """Delete a user's Google Calendar token record."""
    db.query(GoogleCalendarToken).filter(
        GoogleCalendarToken.user_id == user_id
    ).delete()
    db.commit()


def _build_credentials(record: GoogleCalendarToken, db: Session, user_id: int) -> Credentials | None:
    """Build Google credentials, refreshing if needed. Returns None on failure."""
    try:
        creds = Credentials(
            token=decrypt_token(record.access_token),
            refresh_token=decrypt_token(record.refresh_token),
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )

        # Check if token is expired (or has no expiry info — treat as potentially expired)
        needs_refresh = creds.expired or record.token_expiry is None
        if record.token_expiry and record.token_expiry < datetime.now(timezone.utc):
            needs_refresh = True

        if needs_refresh:
            try:
                import requests as requests_lib
                _session = requests_lib.Session()
                _session.timeout = GOOGLE_API_TIMEOUT
                creds.refresh(Request(session=_session))
                record.access_token = encrypt_token(creds.token)
                if creds.expiry:
                    record.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
                db.commit()
            except RefreshError:
                logger.warning("Google token refresh failed for user %s", user_id)
                mark_google_token_invalid(db, user_id)
                return None

        return creds
    except Exception:
        logger.exception("Failed to build Google credentials for user %s", user_id)
        return None


def get_google_busy_times(
    db: Session,
    user_id: int,
    day_start: datetime,
    day_end: datetime,
) -> list[tuple[datetime, datetime]] | None:
    """
    Get busy time ranges from a user's Google Calendar.
    Returns None if no token, token invalid, or any API error (graceful fallback).
    Only returns (start, end) tuples — never event details (GCAL-04).
    """
    record = get_google_tokens(db, user_id)
    if not record:
        logger.info("No Google token record for user %s", user_id)
        return None
    if not record.is_valid:
        logger.info("Google token marked invalid for user %s", user_id)
        return None

    logger.info("Building credentials for user %s (expiry: %s)", user_id, record.token_expiry)
    creds = _build_credentials(record, db, user_id)
    if not creds:
        return None

    try:
        # Use httplib2 with timeout to prevent hanging
        http = httplib2.Http(timeout=GOOGLE_API_TIMEOUT)
        authed_http = AuthorizedHttp(creds, http=http)
        service = build("calendar", "v3", http=authed_http, static_discovery=True)

        body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "timeZone": FESTIVAL_TIMEZONE,
            "items": [{"id": "primary"}],
        }
        result = service.freebusy().query(body=body).execute(num_retries=0)

        busy_ranges = []
        festival_tz = ZoneInfo(FESTIVAL_TIMEZONE)
        for period in result.get("calendars", {}).get("primary", {}).get("busy", []):
            start = datetime.fromisoformat(period["start"])
            end = datetime.fromisoformat(period["end"])
            # Convert to festival local time, then replace tzinfo with UTC
            # to match the grid convention ("wall clock time stored as UTC")
            start = start.astimezone(festival_tz).replace(tzinfo=timezone.utc)
            end = end.astimezone(festival_tz).replace(tzinfo=timezone.utc)
            busy_ranges.append((start, end))

        logger.info(
            "Got %d busy ranges for user %s: %s (raw: %s)",
            len(busy_ranges), user_id,
            [(s.isoformat(), e.isoformat()) for s, e in busy_ranges],
            result.get("calendars", {}).get("primary", {}).get("busy", []),
        )
        return busy_ranges

    except Exception:
        logger.exception("Google freebusy query failed for user %s", user_id)
        # GCAL-06: graceful fallback on any failure
        return None
