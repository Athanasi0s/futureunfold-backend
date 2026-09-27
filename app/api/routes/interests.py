from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.interest import Interest
from app.models.user_interest import UserInterest
from app.api.schemas import InterestOut, SetInterestsIn

router = APIRouter()


@router.get("/interests", response_model=list[InterestOut])
def list_interests(db: Session = Depends(get_db)):
    """Επιστρέφει όλα τα διαθέσιμα interests."""
    interests = db.query(Interest).order_by(Interest.name).all()
    return [InterestOut(id=i.id, name=i.name) for i in interests]


@router.get("/me/interests", response_model=list[InterestOut])
def get_my_interests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Επιστρέφει τα interests του τρέχοντα χρήστη."""
    rows = (
        db.query(Interest)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .filter(UserInterest.user_id == current_user.id)
        .order_by(Interest.name)
        .all()
    )
    return [InterestOut(id=i.id, name=i.name) for i in rows]


@router.put("/me/interests", response_model=list[InterestOut])
def set_my_interests(
    payload: SetInterestsIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Αντικαθιστά τα interests του χρήστη με τα νέα."""
    # Validate interest IDs exist
    if payload.interest_ids:
        existing = (
            db.query(Interest.id)
            .filter(Interest.id.in_(payload.interest_ids))
            .all()
        )
        existing_ids = {row[0] for row in existing}
        invalid = set(payload.interest_ids) - existing_ids
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid interest IDs: {sorted(invalid)}")

    # Delete current interests
    db.query(UserInterest).filter(UserInterest.user_id == current_user.id).delete()

    # Insert new ones
    for interest_id in payload.interest_ids:
        db.add(UserInterest(user_id=current_user.id, interest_id=interest_id))

    db.commit()

    # Return updated list
    rows = (
        db.query(Interest)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .filter(UserInterest.user_id == current_user.id)
        .order_by(Interest.name)
        .all()
    )
    return [InterestOut(id=i.id, name=i.name) for i in rows]
