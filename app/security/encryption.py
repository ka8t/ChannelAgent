"""Application-layer symmetric encryption for sensitive data at rest.

Covers fields such as raw email addresses, Matrix access tokens, and other
personal metadata stored in the database. The encryption key is loaded
dynamically from the environment (see app/config.py) and is never stored
in the database and never committed to Git.

This module intentionally exposes only two functions. Database models
call these directly in their field setters/getters rather than handling
Fernet objects themselves, so the encryption behavior stays in one place.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().encryption_key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string for storage. Returns a token safe for a TEXT column."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    """Decrypt a value previously produced by encrypt_value.

    Raises ValueError on a corrupted token or a key mismatch (e.g. the
    ENCRYPTION_KEY was rotated without re-encrypting existing rows),
    rather than returning garbage bytes.
    """
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt value: invalid token or wrong ENCRYPTION_KEY") from exc
