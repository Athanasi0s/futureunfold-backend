"""
Push notification service — persists notifications to the DB and fires
Expo push messages to all registered tokens for a user.

Usage (from any route or service):

    from app.services.push import send_push

    send_push(
        db=db,
        user_id=target_user.id,
        title="New message",
        body="You have a new DM from Alice",
        notif_type="dm",
        ref_id=message_id,
        data={"screen": "DM", "conversation_id": conversation_id},
    )

The notification is persisted even when the user has no registered token.
The function never raises — Expo errors are swallowed so callers stay clean.
"""

import httpx
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.push_token import PushToken

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_EXPO_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Content-Type": "application/json",
}


def send_push(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    notif_type: str | None = None,
    ref_id: int | None = None,
    deeplink: str | None = None,
    data: dict | None = None,
) -> Notification:
    """
    Persist a notification row and fire Expo push messages for all of the
    user's registered tokens.  Returns the persisted Notification object.
    Callers are responsible for committing the session.
    """
    notif = Notification(
        user_id=user_id,
        title=title,
        body=body,
        type=notif_type,
        ref_id=ref_id,
        deeplink=deeplink,
    )
    db.add(notif)
    db.flush()  # assign notif.id without committing

    tokens = db.query(PushToken).filter(PushToken.user_id == user_id).all()
    if not tokens:
        return notif

    merged_data = {**(data or {}), **({"deeplink": deeplink} if deeplink else {})}
    messages = [
        {
            "to": pt.token,
            "title": title,
            "body": body,
            **({"data": merged_data} if merged_data else {}),
        }
        for pt in tokens
    ]

    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(EXPO_PUSH_URL, json=messages, headers=_EXPO_HEADERS)
    except Exception:
        pass  # never fail the caller because of a push error

    return notif


def send_push_batch(
    db: Session,
    notifications: list[dict],
) -> None:
    """
    Send push notifications to multiple users in batch.

    Each dict in *notifications* must contain:
        user_id (int), title (str), body (str)
    Optional keys: notif_type, ref_id, deeplink, data

    Persists Notification rows and fires Expo pushes in chunks of 100.
    Never raises -- errors are silently swallowed.
    """
    if not notifications:
        return

    # Collect all target user_ids
    user_ids = list({n["user_id"] for n in notifications})

    # Batch-fetch all push tokens for the target users
    tokens_rows = (
        db.query(PushToken)
        .filter(PushToken.user_id.in_(user_ids))
        .all()
    )
    # Build a mapping: user_id -> list of token strings
    tokens_by_user: dict[int, list[str]] = {}
    for pt in tokens_rows:
        tokens_by_user.setdefault(pt.user_id, []).append(pt.token)

    # Persist notification rows and build Expo messages
    expo_messages: list[dict] = []

    for n in notifications:
        uid = n["user_id"]
        title = n["title"]
        body = n["body"]
        deeplink = n.get("deeplink")

        notif = Notification(
            user_id=uid,
            title=title,
            body=body,
            type=n.get("notif_type"),
            ref_id=n.get("ref_id"),
            deeplink=deeplink,
        )
        db.add(notif)

        user_tokens = tokens_by_user.get(uid, [])
        merged_data = {**(n.get("data") or {}), **({"deeplink": deeplink} if deeplink else {})}
        for tok in user_tokens:
            expo_messages.append({
                "to": tok,
                "title": title,
                "body": body,
                **({"data": merged_data} if merged_data else {}),
            })

    db.flush()

    # Send in chunks of 100
    try:
        with httpx.Client(timeout=10.0) as client:
            for i in range(0, len(expo_messages), 100):
                chunk = expo_messages[i : i + 100]
                client.post(EXPO_PUSH_URL, json=chunk, headers=_EXPO_HEADERS)
    except Exception:
        pass  # never fail the caller because of a push error
