from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext

ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 24 ώρες (για development/MVP)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def hash_password(password: str) -> str:
#     return pwd_context.hash(password)

# def verify_password(password: str, password_hash: str) -> bool:
#     return pwd_context.verify(password, password_hash)
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """
    Παίρνει ένα απλό password (κείμενο) και επιστρέφει bcrypt hash.
    Προσοχή: το bcrypt έχει όριο ~72 bytes στο password.
    """
    if password is None:
        raise ValueError("Το password είναι κενό.")

    # Σιγουρευόμαστε ότι είναι string
    if not isinstance(password, str):
        password = str(password)

    # Ασφάλεια: κόβουμε στα 72 bytes (bcrypt limitation)
    # (αν ο χρήστης βάλει τεράστιο password, δεν θέλουμε να σκάει ο server)
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
        password = pw_bytes.decode("utf-8", errors="ignore")

    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Ελέγχει αν το plain_password ταιριάζει με το hashed_password.
    """
    if plain_password is None or hashed_password is None:
        return False

    if not isinstance(plain_password, str):
        plain_password = str(plain_password)

    pw_bytes = plain_password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
        plain_password = pw_bytes.decode("utf-8", errors="ignore")

    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, token_version: int, secret: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "token_version": int(token_version),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)

def decode_token(token: str, secret: str) -> dict:
    """Decode JWT and return {"user_id": int, "token_version": int}.

    Missing `token_version` claim defaults to 0 so that legacy JWTs issued
    before the Phase 11 deploy decode cleanly and match the DB default 0.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        token_version = int(payload.get("token_version", 0))
        return {"user_id": user_id, "token_version": token_version}
    except (JWTError, ValueError) as e:
        raise ValueError("Μη έγκυρο token") from e
