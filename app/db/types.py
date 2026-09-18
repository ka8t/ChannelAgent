"""SQLAlchemy column type that encrypts on write and decrypts on read.

Implements #9: models use EncryptedString for any sensitive field
(raw email address, Matrix access token, other personal metadata)
instead of remembering to call encrypt_value/decrypt_value by hand at
every call site.
"""

from sqlalchemy.types import String, TypeDecorator

from app.security.encryption import decrypt_value, encrypt_value


class EncryptedString(TypeDecorator):
    """A TEXT column that transparently encrypts/decrypts its Python value.

    A Fernet token is longer than its plaintext and varies in length
    with the key/nonce, so this is stored as unbounded TEXT regardless
    of the logical field's plaintext length.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return decrypt_value(value)
