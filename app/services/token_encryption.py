from cryptography.fernet import Fernet
from app.core.config import GOOGLE_TOKEN_ENCRYPTION_KEY

_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not GOOGLE_TOKEN_ENCRYPTION_KEY:
            raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY not set")
        _fernet = Fernet(GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
