from typing import Generator
from app.db.session import SessionLocal

# Dependency: σε κάθε request ανοίγουμε μία σύνδεση (session) στη βάση και στο τέλος την κλείνουμε.
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.config import JWT_SECRET
from app.core.security import decode_token
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Επιστρέφει τον τρέχοντα χρήστη από το Bearer token."""
    if creds is None:
        raise HTTPException(status_code=401, detail="Χρειάζεται σύνδεση (login).")

    token = creds.credentials
    try:
        decoded = decode_token(token, JWT_SECRET)
    except ValueError:
        raise HTTPException(status_code=401, detail="Μη έγκυρο token.")

    user_id = decoded["user_id"]
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Ο χρήστης δεν βρέθηκε.")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail={"error": "account_blocked", "message": "Your account has been suspended"})
    # Phase 11: token_version mismatch → session ended (role change, forced logout).
    # Legacy JWTs without the claim decode to token_version=0; DB default is 0, so they pass.
    if (user.token_version or 0) != decoded["token_version"]:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "token_invalidated",
                "message": "Your session ended because your role changed. Please sign in again.",
            },
        )
    return user


def get_user_from_token(token: str, db: Session) -> User:
    """Resolve a user from a raw JWT string (no FastAPI Depends)."""
    decoded = decode_token(token, JWT_SECRET)
    user_id = decoded["user_id"]
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    # Phase 11: same token_version invariant as get_current_user.
    if (user.token_version or 0) != decoded["token_version"]:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "token_invalidated",
                "message": "Your session ended because your role changed. Please sign in again.",
            },
        )
    return user


def get_optional_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Return the current user if authenticated, otherwise None."""
    if creds is None:
        return None

    token = creds.credentials
    try:
        decoded = decode_token(token, JWT_SECRET)
    except ValueError:
        return None

    user_id = decoded["user_id"]
    user = db.get(User, user_id)
    if user and user.is_blocked:
        return None
    # Phase 11: stale token_version silently returns None (no raise — this is the optional dep).
    if user and (user.token_version or 0) != decoded["token_version"]:
        return None
    return user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Raises 403 if the current user is not an admin."""
    from app.core.enums import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admin access required."
        )
    return current_user


def require_feature(flag: str):
    """Factory returning a FastAPI dependency that checks if a feature flag is enabled.

    Note: Each gated request issues one DB query for AppConfig("feature_flags").
    This is acceptable at festival scale (~1000 concurrent users). For higher scale,
    implement a TTL cache on get_merged_flags().
    """
    from app.core.feature_flags import get_merged_flags

    def checker(db: Session = Depends(get_db)):
        flags = get_merged_flags(db)
        if not flags.get(flag, True):
            raise HTTPException(
                status_code=403,
                detail={"error": "feature_disabled", "feature": flag},
            )

    return Depends(checker)


def require_moderator_scope(scope_key: str):
    """Factory: returns a FastAPI dependency callable resolving to the current User
    iff role==admin OR (role==moderator AND moderator_permissions[scope_key] is True).

    Usage pattern (matches `require_admin`):

        current_user: User = Depends(require_moderator_scope('ticket_packages'))

    The factory returns the bare checker function — the caller wraps it in
    `Depends(...)` in the endpoint signature. `current_user.id` is the correct
    audit subject regardless of whether the acting user is admin or moderator.
    """
    from app.core.enums import UserRole
    from app.core.moderator_permissions import get_moderator_permissions

    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role == UserRole.admin:
            return current_user
        if current_user.role == UserRole.moderator:
            perms = get_moderator_permissions(db)
            if perms.get(scope_key, False):
                return current_user
        raise HTTPException(status_code=403, detail={"error": "forbidden"})

    return checker
