# app/api/routes/qr.py
"""
QR-code & points endpoints.
- GET  /qr/me         → authenticated user's QR token + points
- POST /qr/scan       → scan another user's QR code (awards points when exhibitor→attendee)
- GET  /qr/history    → scan history for the authenticated user (as scanner)
- GET  /qr/leaderboard → top users by points
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Literal
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.core.deps import get_db, get_current_user, require_feature
from app.core.enums import UserRole
from app.models.user import User
from app.models.scan_log import ScanLog
from app.api.schemas import (
    QrCodeOut,
    ScanIn,
    ScanOut,
    ScanLogOut,
    LeaderboardEntryOut,
)
from app.services.rewards import award_points

router = APIRouter(dependencies=[require_feature("digital_id")])

EXHIBITOR_SCAN_POINTS = 10  # Points awarded when an exhibitor scans an attendee


# ──────────────────────────────────────
# GET /qr/me — my QR code & points
# ──────────────────────────────────────
@router.get("/qr/me", response_model=QrCodeOut)
def get_my_qr(current_user: User = Depends(get_current_user)):
    """Επιστρέφει το user id (για QR) και τους πόντους του τρέχοντα χρήστη."""
    return QrCodeOut(user_id=current_user.id, points=current_user.points)


# ──────────────────────────────────────
# POST /qr/scan — scan a QR code
# ──────────────────────────────────────
@router.post("/qr/scan", response_model=ScanOut)
def scan_qr(
    payload: ScanIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Σκανάρει το QR-code ενός άλλου χρήστη.
    Αν ο scanner είναι exhibitor και ο scanned είναι attendee → +10 πόντοι στον attendee.
    Κάθε ζευγάρι scanner→scanned επιτρέπεται μόνο μία φορά.
    """

    # 1) Βρες τον χρήστη από το user id (QR code = user id)
    scanned_user = db.get(User, payload.user_id)
    if not scanned_user:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε χρήστης με αυτό το id.")

    # 2) Δεν μπορείς να σκανάρεις τον εαυτό σου
    if scanned_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Δεν μπορείς να σκανάρεις τον εαυτό σου.")

    # 3) Έλεγχος duplicate scan
    existing = (
        db.query(ScanLog)
        .filter(
            ScanLog.scanner_id == current_user.id,
            ScanLog.scanned_id == scanned_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Έχεις ήδη σκανάρει αυτόν τον χρήστη.")

    # 4) Υπολογισμός πόντων
    points = 0
    if current_user.role == UserRole.exhibitor and scanned_user.role == UserRole.attendee:
        points = EXHIBITOR_SCAN_POINTS

    # 5) Δημιουργία scan log
    scan = ScanLog(
        scanner_id=current_user.id,
        scanned_id=scanned_user.id,
        points_awarded=points,
    )
    db.add(scan)

    # 6) Award points via reward service (creates PointTransaction record)
    if points > 0:
        award_points(db, scanned_user.id, "QR_SCAN", points, source_ref=str(current_user.id))

    db.commit()
    db.refresh(scan)
    db.refresh(scanned_user)

    # 7) Μήνυμα απόκρισης
    if points > 0:
        message = f"Scan επιτυχές! +{points} πόντοι στον {scanned_user.full_name or 'χρήστη'}."
    else:
        message = "Scan καταγράφηκε επιτυχώς."

    return ScanOut(
        scan_id=scan.id,
        scanned_user_id=scanned_user.id,
        scanned_user_name=scanned_user.full_name,
        points_awarded=points,
        scanner_total_points=current_user.points or 0,
        scanned_total_points=scanned_user.points or 0,
        message=message,
    )


# ──────────────────────────────────────
# GET /qr/history — my scan history
# ──────────────────────────────────────
@router.get("/qr/history", response_model=list[ScanLogOut])
def get_scan_history(
    direction: Literal["all", "scanned_by_me", "scanned_me"] = Query(
        default="all",
        description=(
            "all — all scans involving me; "
            "scanned_by_me — users I have scanned; "
            "scanned_me — users who scanned me"
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Επιστρέφει το ιστορικό scans του τρέχοντα χρήστη φιλτραρισμένο ανά κατεύθυνση."""
    if direction == "scanned_by_me":
        condition = ScanLog.scanner_id == current_user.id
    elif direction == "scanned_me":
        condition = ScanLog.scanned_id == current_user.id
    else:
        condition = (ScanLog.scanner_id == current_user.id) | (ScanLog.scanned_id == current_user.id)

    scans = (
        db.query(ScanLog)
        .filter(condition)
        .order_by(ScanLog.created_at.desc())
        .all()
    )

    return [
        ScanLogOut(
            id=s.id,
            scanner_id=s.scanner_id,
            scanner_name=s.scanner.full_name if s.scanner else None,
            scanned_id=s.scanned_id,
            scanned_name=s.scanned.full_name if s.scanned else None,
            points_awarded=s.points_awarded,
            created_at=s.created_at.isoformat(),
        )
        for s in scans
    ]


# ──────────────────────────────────────
# GET /qr/leaderboard — top users by points
# ──────────────────────────────────────
@router.get("/qr/leaderboard", response_model=list[LeaderboardEntryOut])
def get_leaderboard(
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Επιστρέφει τους χρήστες με τους περισσότερους πόντους."""
    users = (
        db.query(User)
        .filter(User.points > 0)
        .order_by(User.points.desc())
        .limit(limit)
        .all()
    )

    return [
        LeaderboardEntryOut(
            user_id=u.id,
            full_name=u.full_name,
            role=u.role.value if u.role else "attendee",
            points=u.points or 0,
            rank=idx + 1,
        )
        for idx, u in enumerate(users)
    ]
