"""
Notifications API routes.

Endpoints:
- POST   /notifications/push-token       → register Expo push token for current device
- DELETE /notifications/push-token       → remove a push token
- GET    /notifications                  → list current user's notifications (newest first)
- GET    /notifications/unseen-count     → count of unseen notifications
- PATCH  /notifications/{id}/seen        → mark a single notification as seen
- POST   /notifications/mark-all-seen   → mark all notifications as seen
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError

from app.core.deps import get_db, get_current_user, require_feature
from app.models.user import User
from app.models.push_token import PushToken
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.api.schemas import (
    PushTokenIn,
    NotificationOut,
    UnseenCountOut,
    PreferenceOut,
    PreferenceUpdateItem,
)

router = APIRouter(dependencies=[require_feature("notifications")])


# ──────────────────────────────────────
# POST /notifications/push-token
# ──────────────────────────────────────
@router.post("/notifications/push-token", status_code=204)
def register_push_token(
    body: PushTokenIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Αποθηκεύει ένα Expo push token για τον τρέχοντα χρήστη/συσκευή.

    Phase 13: αποθηκεύει επίσης το platform ('ios'|'android'|'web') όταν
    αποστέλλεται, ώστε το /admin/push/broadcast να επιστρέφει device breakdown (PUSH-04).
    """
    existing = (
        db.query(PushToken)
        .filter(PushToken.user_id == current_user.id, PushToken.token == body.token)
        .first()
    )
    if existing:
        # Re-registration από την ίδια συσκευή: αν το platform έχει αλλάξει
        # (π.χ. νέα εγκατάσταση σε άλλο OS) ενημερώνουμε την εγγραφή.
        if body.platform is not None and existing.platform != body.platform:
            existing.platform = body.platform
            db.commit()
        return

    db.add(PushToken(
        user_id=current_user.id,
        token=body.token,
        platform=body.platform,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


# ──────────────────────────────────────
# DELETE /notifications/push-token
# ──────────────────────────────────────
@router.delete("/notifications/push-token", status_code=204)
def remove_push_token(
    body: PushTokenIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Αφαιρεί ένα Expo push token (π.χ. κατά το logout)."""
    db.query(PushToken).filter(
        PushToken.user_id == current_user.id,
        PushToken.token == body.token,
    ).delete(synchronize_session=False)
    db.commit()


# ──────────────────────────────────────
# GET /notifications/unseen-count
# ──────────────────────────────────────
@router.get("/notifications/unseen-count", response_model=UnseenCountOut)
def get_unseen_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει πόσες μη-αναγνωσμένες ειδοποιήσεις έχει ο χρήστης."""
    count = (
        db.query(sa_func.count(Notification.id))
        .filter(Notification.user_id == current_user.id, Notification.seen == False)  # noqa: E712
        .scalar()
        or 0
    )
    return UnseenCountOut(count=count)


# ──────────────────────────────────────
# Notification preference categories
# ──────────────────────────────────────
NOTIFICATION_CATEGORIES = [
    "session_reminder",
    "meeting_reminder",
    "friend_activity",
    "group_suggestion",
    "popular_session",
]


# ──────────────────────────────────────
# GET /notifications/preferences
# ──────────────────────────────────────
@router.get("/notifications/preferences", response_model=list[PreferenceOut])
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return notification preferences for all 5 categories (missing rows default to enabled)."""
    existing = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == current_user.id)
        .all()
    )
    prefs_map = {p.category: p.enabled for p in existing}

    return [
        PreferenceOut(
            category=cat,
            enabled=prefs_map.get(cat, True),
        )
        for cat in NOTIFICATION_CATEGORIES
    ]


# ──────────────────────────────────────
# PUT /notifications/preferences
# ──────────────────────────────────────
@router.put("/notifications/preferences", response_model=list[PreferenceOut])
def update_preferences(
    items: list[PreferenceUpdateItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert notification preference rows for the current user."""
    for item in items:
        if item.category not in NOTIFICATION_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {item.category}",
            )

        existing = (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == current_user.id,
                NotificationPreference.category == item.category,
            )
            .first()
        )
        if existing:
            existing.enabled = item.enabled
        else:
            db.add(
                NotificationPreference(
                    user_id=current_user.id,
                    category=item.category,
                    enabled=item.enabled,
                )
            )

    db.commit()

    # Return full preferences after update
    return get_preferences(db=db, current_user=current_user)


# ──────────────────────────────────────
# GET /notifications
# ──────────────────────────────────────
@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Επιστρέφει τις ειδοποιήσεις του χρήστη (νεότερες πρώτα)."""
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return [_to_out(n) for n in rows]


# ──────────────────────────────────────
# PATCH /notifications/{id}/seen
# ──────────────────────────────────────
@router.patch("/notifications/{notification_id}/seen", response_model=NotificationOut)
def mark_seen(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Σημειώνει μία ειδοποίηση ως αναγνωσμένη."""
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.seen = True
    db.commit()
    db.refresh(notif)
    return _to_out(notif)


# ──────────────────────────────────────
# POST /notifications/mark-all-seen
# ──────────────────────────────────────
@router.post("/notifications/mark-all-seen", status_code=204)
def mark_all_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Σημειώνει όλες τις ειδοποιήσεις του χρήστη ως αναγνωσμένες."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.seen == False,  # noqa: E712
    ).update({"seen": True}, synchronize_session=False)
    db.commit()


# ──────────────────────────────────────
# POST /notifications/test
# ──────────────────────────────────────
@router.post("/notifications/test", response_model=NotificationOut)
def test_push(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Στέλνει ένα test push notification στον τρέχοντα χρήστη."""
    from app.services.push import send_push

    notif = send_push(
        db=db,
        user_id=current_user.id,
        title="Test Notification",
        body="Push notifications are working correctly!",
        notif_type="system",
        deeplink="panathenea://notifications",
    )
    db.commit()
    db.refresh(notif)
    return _to_out(notif)


# ── helper ────────────────────────────
def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        title=n.title,
        body=n.body,
        type=n.type,
        ref_id=n.ref_id,
        deeplink=n.deeplink,
        seen=n.seen,
        created_at=n.created_at.isoformat(),
    )
